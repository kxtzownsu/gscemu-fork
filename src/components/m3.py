# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer
"""The component handler for the M3 component

The Cr50 runs an Arm SC300 CortexM3 armv7m CPU.
Since this is the CPU, it is tightly integrated with the Uc engine. Therefore,
this will not be threaded/queued. Instead, we will have one mutex.
"""

import typing
import time
import unicorn as qemu
import threading
import queue

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from lib.threadutils import FifoLock
from src.emulators.haven.registers import M3_REGS
from lib.helpers import (
    unhandled_register_io, 
    unhandled_register_exit,
    idx_regs_to_regmap,
    args_lambda_gen,
    armv7m_find_instruction_size,
    write_u32_to_sp,
    read_u32_from_sp,
)

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

_CYCCNT_SPEED = (1/24000000) * 1000000000
_EXC_RETURN_VALS = [0xFFFFFFF0, 0xFFFFFFF2, 0xFFFFFFF4]

class ArmInterruptHandler:
    def __init__(self, arm_cpu):
        self.cpu = arm_cpu # We need this to read the VTOR addr for interrupts.

        self.intr_thread = None
        self.intr_queue = queue.Queue()

        self.nvic_pend_lock = threading.Lock()

        self.nvic_en = [0] * (32 * 8) # ISER/ICER
        self.nvic_pend = [0] * (32 * 8) # ISPR/ICPR
        self.nvic_pri = [0] * (32 * 8) # IPR

        # Store system exception pends in a seperate dictionary.
        self.nvic_sys_pend = [0] * 16
        self.nvic_sys_pri = [
            # Fixed priority levels
            -3, # Reset
            -2, # NMI
            -1, # HardFault
        ] + ([0] * (13))

        # TODO(appleflyer): We need a way to send a signal when these values 
        # change. Polling the values with UC_HOOK_CODE is too slow.
        self.primask = 0
        self.faultmask = 0

        self.winning_exception_lock = threading.Lock()
        self.winning_exception = 0

        # We need this variable to track if the interrupt was software or
        # "hardware" triggered, so that we can safely branch to
        # exceptions. This variable should only be read in the
        # branch_to_exception function, and nowhere else.
        self.internal_exception_trig = False

    def m3_intr_worker(self):
        while True:
            try:
                target_fn, internal_trig, args = self.intr_queue.get()
                self.internal_exception_trig = internal_trig

                # Process the interrupt op
                target_fn(*args)

                # After processing the interrupt op, we need to check if we have
                # any pending interrupts that can be activated.
                pending_exceptions = {}
                self.check_for_pending_exceptions(pending_exceptions)

                if not pending_exceptions:
                    self.intr_queue.task_done()
                    continue

                # There are exceptions pending. Check if we should branch to any
                # of them.
                winning_exception = (
                    self.should_trigger_exception(pending_exceptions)
                )

                if winning_exception == -1:
                    self.intr_queue.task_done()
                    continue
            
                # If we are still here, it means we need to branch to
                # winning_exc exception.
                self.branch_to_exception(winning_exception)

                self.intr_queue.task_done()

            except Exception as e:
                prints.fatal(e)

    def start_intr_worker(self) -> None:
        self.intr_thread = threading.Thread(target=self.m3_intr_worker)
        self.intr_thread.daemon = True
        self.intr_thread.start()

    def queue_internal_read_worker_op(self, size: int, target_fn):
        retqueue = queue.Queue()
        self.intr_queue.put([target_fn, True, (size, retqueue)])
        self.intr_queue.join()
        return retqueue.get_nowait()
        
    def queue_internal_write_worker_op(self, size: int, value: int, target_fn):
        self.intr_queue.put([target_fn, True, (size, value)])
        self.intr_queue.join()

    def queue_exc_return(self):
        self.intr_queue.put([self.exc_return_callback, False, tuple()])
        self.intr_queue.join()

    def exc_return_callback(self) -> None:
        address = ucmutex().reg_read(qemu.arm_const.UC_ARM_REG_PC)
        if address == _EXC_RETURN_VALS[0] or address == _EXC_RETURN_VALS[1]:
            sp_type = qemu.arm_const.UC_ARM_REG_MSP
        elif address == _EXC_RETURN_VALS[2]:
            sp_type = qemu.arm_const.UC_ARM_REG_PSP

        if ucmutex().reg_read(qemu.arm_const.UC_ARM_REG_IPSR) != 2:
            ucmutex().reg_write(qemu.arm_const.UC_ARM_REG_FAULTMASK, 0)

        for reg in reversed([
            qemu.arm_const.UC_ARM_REG_XPSR,
            qemu.arm_const.UC_ARM_REG_PC,
            qemu.arm_const.UC_ARM_REG_LR,
            qemu.arm_const.UC_ARM_REG_R12,
            qemu.arm_const.UC_ARM_REG_R3,
            qemu.arm_const.UC_ARM_REG_R2,
            qemu.arm_const.UC_ARM_REG_R1,
            qemu.arm_const.UC_ARM_REG_R0,
        ]):
            reg_val = read_u32_from_sp(ucmutex(), sp_type)
            ucmutex().reg_write(reg, reg_val)

    def check_for_pending_exceptions(self, pending_exceptions: dict) -> None:
        # Populate pending_exceptions with pending exceptions.
        # exception_num: priority
        
        # PRIMASK disables IRQs
        if not self.faultmask:
            if not self.primask:
                with self.nvic_pend_lock:
                    for irq in range(len(self.nvic_pend)):
                        if not self.nvic_pend[irq]:
                            continue
                        if not self.nvic_en[irq]:
                            continue
                        pending_exceptions[irq + 16] = (
                            self.nvic_pri[irq]
                        )
                
                for exc in range(len(self.nvic_sys_pend)):
                    if not self.nvic_sys_pend[exc]:
                        continue
                    pending_exceptions[exc] = self.nvic_sys_pri[exc]

        # FAULTMASK is set, all exceptions disabled NMI.
        else:
            if self.nvic_sys_pend[2]:
                pending_exceptions[2] = self.nvic_sys_pri[2]

    def should_trigger_exception(self, pending_exceptions: dict) -> int:
        # First, find a winning exception out of all the pending
        # exceptions.
        winning_exc = min(
            pending_exceptions.items(), 
            key=lambda x: (x[1], x[0])
        )
        winning_exc_num, winning_exc_pri = winning_exc

        # Second, check if we are in an exception. If so, check its priority 
        # level to see if it's lower than our winning_exc.
        current_exc_num = g_uc().reg_read(
            qemu.arm_const.UC_ARM_REG_IPSR
        )
            
        if current_exc_num:
            # We are in an exception. Check it's priority level.
            if current_exc_num >= 16:
                current_exc_priority = self.nvic_pri[current_exc_num - 16]
            else:
                current_exc_priority = self.nvic_sys_pri[current_exc_num]
            
            if winning_exc_pri >= current_exc_priority:
                # The current winning exception priority isn't low enough. Do
                # not trigger another stacked exception.
                return -1
            
        # We aren't in an exception.
        return winning_exc_num
    
    def branch_to_exception(self, exception_num: int) -> None:
        ret_pc = ucmutex().reg_read(qemu.arm_const.UC_ARM_REG_PC)

        # On an internal exception trigger, we need to advance the PC. The write
        # has been completed, but the PC has not been advanced yet.
        # On an external exception trigger, we don't have to advance the PC.
        # The emulator already steps the PC without executing the next inst.
        # On an EXC_RETURN callback, we will just 
        # self.internal_exception_trig = False, because the PC has already been
        # advanced.
        if self.internal_exception_trig:
            ret_pc += armv7m_find_instruction_size(ucmutex(), ret_pc)

        ucmutex().reg_write(qemu.arm_const.UC_ARM_REG_PC, ret_pc|1)

        current_mode = None
        current_sp = None
        built_exc_return = None
        if ucmutex().reg_read(
            qemu.arm_const.UC_ARM_REG_CONTROL
        ) & 2: # thread = psp, handler = msp
            if ucmutex().reg_read(qemu.arm_const.UC_ARM_REG_IPSR): # handler
                current_mode = "handler"
                current_sp = "msp"
            else: # thread
                current_mode = "thread"
                current_sp = "psp"
        else: # thread = msp, handler = msp
            if ucmutex().reg_read(qemu.arm_const.UC_ARM_REG_IPSR): # handler
                current_mode = "handler"
            else: # thread
                current_mode = "thread"
            current_sp = "msp"

        # EXC_RETURN value determination
        if current_mode == "thread":
            if current_sp == "msp":
                built_exc_return = _EXC_RETURN_VALS[1]
            elif current_sp == "psp":
                built_exc_return = _EXC_RETURN_VALS[2]
        elif current_mode == "handler":
            if current_sp == "msp":
                built_exc_return = _EXC_RETURN_VALS[0]
            elif current_sp == "psp":
                prints.fatal_exit(
                    "impossible handler+psp case for EXC_RETURN!!!"
                )

        # push exception frame to the stack
        for reg in [qemu.arm_const.UC_ARM_REG_XPSR,
                    qemu.arm_const.UC_ARM_REG_PC,
                    qemu.arm_const.UC_ARM_REG_LR,
                    qemu.arm_const.UC_ARM_REG_R12,
                    qemu.arm_const.UC_ARM_REG_R3,
                    qemu.arm_const.UC_ARM_REG_R2,
                    qemu.arm_const.UC_ARM_REG_R1,
                    qemu.arm_const.UC_ARM_REG_R0]:
            reg_val = ucmutex().reg_read(reg)
            if reg == qemu.arm_const.UC_ARM_REG_PC:
                reg_val |= 1
            write_u32_to_sp(ucmutex(), reg_val)
        
        # place EXC_RETURN val and enter handler mode
        ucmutex().reg_write(qemu.arm_const.UC_ARM_REG_LR, built_exc_return|1)
        ucmutex().reg_write(qemu.arm_const.UC_ARM_REG_IPSR, exception_num)

        # IT state is cleared, as documented in the ARM psuedocode
        # EPSR.IT<7:0> = Zeros(8);
        ucmutex().reg_write(
            qemu.arm_const.UC_ARM_REG_EPSR, 
            ucmutex().reg_read(qemu.arm_const.UC_ARM_REG_EPSR) & ~0x600fc00
        )

        # Generate the handler's PC based on the VTOR address
        exception_pc = ucmutex().int32_mem_read(
            self.cpu.vtor + exception_num * 4
        )

        ucmutex().reg_write(qemu.arm_const.UC_ARM_REG_PC, exception_pc)

        if exception_num >= 16:
            with self.nvic_pend_lock:
                self.nvic_pend[exception_num - 16] = False
        elif exception_num < 16:
            self.nvic_sys_pend[exception_num - 1] = False
        
    def read_iser(self, size: int, queue: queue.Queue, index: int) -> None:
        value = 0
        base = index * 32
        for bit in range(32):
            if self.nvic_en[base + bit]:
                value |= (1 << bit)
        queue.put(value)

    def write_iser(self, size: int, value: int, index: int) -> None:
        base = index * 32
        for bit in range(32):
            if (value >> bit) & 1:
                self.nvic_en[base + bit] = True

    def read_icer(self, size: int, queue: queue.Queue, index: int) -> None:
        value = 0
        base = index * 32
        for bit in range(32):
            if self.nvic_en[base + bit]:
                value |= (1 << bit)
        queue.put(value)

    def write_icer(self, size: int, value: int, index: int) -> None:
        base = index * 32
        for bit in range(32):
            if (value >> bit) & 1:
                self.nvic_en[base + bit] = False

    def read_ispr(self, size: int, queue: queue.Queue, index: int) -> None:
        value = 0
        base = index * 32
        for bit in range(32):
            if self.nvic_pend[base + bit]:
                value |= (1 << bit)
        queue.put(value)

    def write_ispr(self, size: int, value: int, index: int) -> None:
        base = index * 32
        for bit in range(32):
            if (value >> bit) & 1:
                self.nvic_pend[base + bit] = True

    def read_icpr(self, size: int, queue: queue.Queue, index: int) -> None:
        value = 0
        base = index * 32
        for bit in range(32):
            if self.nvic_pend[base + bit]:
                value |= (1 << bit)
        queue.put(value)

    def write_icpr(self, size: int, value: int, index: int) -> None:
        base = index * 32
        for bit in range(32):
            if (value >> bit) & 1:
                self.nvic_pend[base + bit] = False

    def read_ipr(self, size: int, queue: queue.Queue, index: int) -> None:
        value = 0
        base = index * 4
        for byte in range(4):
            value |= (((self.nvic_pri[base + byte] & 0x7) << 5) << (byte * 8))

        queue.put(value)

    def write_ipr(self, size: int, value: int, index: int) -> None:
        base = index * 4
        for byte in range(4):            
            self.nvic_pri[base + byte] = (
                (((value >> (byte * 8)) & 0xFF) >> 5) & 0x7
            )

    def read_stir(self, size: int, queue: queue.Queue) -> None:
        unhandled_register_io(prints, "READ", "NVIC_STIR", "M3")
        queue.put(0)

    def write_stir(self, size: int, value: int) -> None:
        # 0x1FF as of ARM spec which states that bits 9 - 32 are reserved.
        self.nvic_pend[value & 0x1FF] = True

class ArmSC300:
    def __init__(self):
        self.mutex = FifoLock()
        self.cpuid = 0x410fc331 # Known CPUID for the ArmSC300

        self.intr_op = ArmInterruptHandler(self)
        self.intr_op.start_intr_worker()

        self.cyccnt_time_start = 0
        self.itcmcr = 0
        self.demcr = 0
        self.shscr = 0
        self.ccr = 0
        self.dwt_ctrl = 0
        self.vtor = 0

    def start_cyccnt_time(self) -> None:
        with self.mutex:
            self.cyccnt_time_start = time.perf_counter_ns()

    def read_demcr(self, size: int) -> None:
        with self.mutex:
            return self.demcr

    def write_demcr(self, size: int, value: int) -> None:
        with self.mutex:
            self.demcr = value

    def read_dwt_ctrl(self, size: int) -> None:
        with self.mutex:
            return self.dwt_ctrl

    def write_dwt_ctrl(self, size: int, value: int) -> None:
        with self.mutex:
            self.dwt_ctrl = value

    def read_cpuid(self, size: int) -> None:
        with self.mutex:
            return self.cpuid

    def write_cpuid(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "M3", "CPUID")

    def read_vtor(self, size: int) -> None:
        with self.mutex:
            return self.vtor

    def write_vtor(self, size: int, value: int) -> None:
        with self.mutex:
            self.vtor = value

    def read_shscr(self, size: int) -> None:
        with self.mutex:
            return self.shscr

    def write_shscr(self, size: int, value: int) -> None:
        with self.mutex:
            self.shscr = value

    def read_ccr(self, size: int) -> None:
        with self.mutex:
            return self.ccr

    def write_ccr(self, size: int, value: int) -> None:
        with self.mutex:
            self.ccr = value

    def read_itcmcr(self, size: int) -> None:
        with self.mutex:
            return self.itcmcr

    def write_itcmcr(self, size: int, value: int) -> None:
        with self.mutex:
            # It is unknown why ITCMCR returns 7. We need to figure it out.
            self.itcmcr = 7

    def read_dwt_cyccnt(self, size: int) -> None:
        with self.mutex:
            val = int(
                (time.perf_counter_ns() - self.cyccnt_time_start) 
                // _CYCCNT_SPEED
            )
            return val

    def write_dwt_cyccnt(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "M3", "DWT_CYCCNT")

c_emu = ArmSC300()

_REG_FUNC_MAP = {
    M3_REGS["DEMCR"]: [c_emu.read_demcr, c_emu.write_demcr],
    M3_REGS["DWT_CTRL"]: [c_emu.read_dwt_ctrl, c_emu.write_dwt_ctrl],
    M3_REGS["CPUID"]: [c_emu.read_cpuid, c_emu.write_cpuid],
    M3_REGS["ITCMCR"]: [c_emu.read_itcmcr, c_emu.write_itcmcr],
    M3_REGS["DWT_CYCCNT"]: [c_emu.read_dwt_cyccnt, c_emu.write_dwt_cyccnt],
    M3_REGS["VTOR"]: [c_emu.read_vtor, c_emu.write_vtor],
    M3_REGS["CCR"]: [c_emu.read_ccr, c_emu.write_ccr],
    M3_REGS["SHSCR"]: [c_emu.read_shscr, c_emu.write_shscr],
}

_INTR_FUNC_MAP = {
    M3_REGS["NVIC_STIR"]: [c_emu.intr_op.read_stir, c_emu.intr_op.write_stir],
}

idx_regs_to_regmap(
    _INTR_FUNC_MAP, M3_REGS["NVIC_ISER"],
    c_emu.intr_op.read_iser, c_emu.intr_op.write_iser
)

idx_regs_to_regmap(
    _INTR_FUNC_MAP, M3_REGS["NVIC_ICER"],
    c_emu.intr_op.read_icer, c_emu.intr_op.write_icer
)

idx_regs_to_regmap(
    _INTR_FUNC_MAP, M3_REGS["NVIC_ICPR"],
    c_emu.intr_op.read_icpr, c_emu.intr_op.write_icpr
)

idx_regs_to_regmap(
    _INTR_FUNC_MAP, M3_REGS["NVIC_IPR"],
    c_emu.intr_op.read_ipr, c_emu.intr_op.write_ipr
)

for k, v in _INTR_FUNC_MAP.items():
    _REG_FUNC_MAP[k] = [
        args_lambda_gen(c_emu.intr_op.queue_internal_read_worker_op, v[0]), 
        args_lambda_gen(c_emu.intr_op.queue_internal_write_worker_op, v[1])
    ]

def exc_return_handler() -> None:
    c_emu.intr_op.queue_exc_return()

def component_read_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    user_data: typing.Any,
) -> int:
    try:
        return _REG_FUNC_MAP[offset][0](size)
    except KeyError:
        unhandled_register_exit(g_uc(), ucthread(), prints, "M3", offset)

def component_write_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    value: int,
    user_data: typing.Any,
) -> None:
    try:
        _REG_FUNC_MAP[offset][1](size, value)
    except KeyError:
        unhandled_register_exit(g_uc(), ucthread(), prints, "M3", offset)