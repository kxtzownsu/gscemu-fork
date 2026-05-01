# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer
"""The component handler for the M3 component

The Cr50 runs an Arm SC300 CortexM3 armv7m CPU.
Since this is the CPU, it is tightly integrated with the Uc engine. Therefore,
this will not be threaded/queued. Instead, we will have one mutex.
"""

import queue
import threading
import time
import typing

import unicorn as qemu

from env import *
from lib.emulator_context import ComponentObjects, EmulatorContext
from lib.helpers import (
    args_lambda_gen,
    armv7m_find_instruction_size,
    idx_regs_to_regmap,
    read_u32_from_sp,
    unhandled_register_exit,
    unhandled_register_io,
    write_u32_to_sp,
)
from lib.logger import GscemuLogger
from lib.threadutils import FifoLock

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

# We need this for components that we may not handle.
_CUSTOM_AUTOUNPEND = [
    207  # UART2_TXINT
]

_CYCCNT_SPEED = (1 / 24000000) * 1000000000
_EXC_RETURN_VALS = [0xFFFFFFF1, 0xFFFFFFF9, 0xFFFFFFFD]


class ArmInterruptHandler:
    def __init__(self, arm_cpu):
        # We need this to read the VTOR addr for interrupts.
        self.cpu = arm_cpu
        self.ctx = self.cpu.ctx

        self.intr_thread = None
        self.intr_queue = queue.Queue()

        self.nvic_pend_lock = threading.Lock()

        self.nvic_en = [0] * (32 * 8)  # ISER/ICER
        self.nvic_pend = [0] * (32 * 8)  # ISPR/ICPR
        self.nvic_pri = [0] * (32 * 8)  # IPR

        # Store system exception pends in a seperate dictionary.
        self.nvic_sys_pend = [0] * 15
        self.nvic_sys_pri = [
            # Fixed priority levels
            -3,  # Reset
            -2,  # NMI
            -1,  # HardFault
        ] + ([0] * (12))

        # TODO(appleflyer): We need a way to send a signal when these values
        # change. Polling the values with UC_HOOK_CODE is too slow.
        self.primask = 0
        self.faultmask = 0

        self.winning_exception_lock = threading.Lock()
        self.winning_exception = 0

        # We need this variable to track when to increment the return pc,
        # depending on whether the interrupt was triggered from an internal
        # register write or a safe-point hook.
        self.intr_ctx_increment_pc = False
        self.external_interrupt_pending = threading.Event()

    def m3_intr_worker(self):
        while True:
            try:
                target_fn, ctx_ipc, args = self.intr_queue.get()
                self.intr_ctx_increment_pc = ctx_ipc

                # Process the interrupt op
                if target_fn:
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
                winning_exception = self.should_trigger_exception(
                    pending_exceptions
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

    def queue_internal_read_worker_op(
        self, size: int, target_fn: typing.Callable
    ) -> None:
        retqueue = queue.Queue()
        self.intr_queue.put(
            [
                target_fn,
                True,  # increment_pc
                (size, retqueue),
            ]
        )
        self.intr_queue.join()
        return retqueue.get_nowait()

    def queue_internal_write_worker_op(
        self, size: int, value: int, target_fn: typing.Callable
    ):
        self.intr_queue.put(
            [
                target_fn,
                True,  # increment_pc
                (size, value),
            ]
        )
        self.intr_queue.join()

    def queue_exc_return(self) -> None:
        self.intr_queue.put(
            [
                self.exc_return_callback,
                False,  # increment_pc
                tuple(),
            ]
        )
        self.intr_queue.join()

    def queue_svcall_interrupt(self) -> None:
        self.intr_queue.put(
            [
                self.pend_svcall_interrupt,
                False,  # increment_pc
                tuple(),
            ]
        )
        self.intr_queue.join()

    def queue_unsafe_pend_external_irq(self) -> None:
        self.intr_queue.put(
            [
                self.unsafe_pend_external_irq,
                False,  # increment_pc
                tuple(),
            ]
        )
        self.intr_queue.join()

    def queue_unsafe_unpend_external_irq(self) -> None:
        self.intr_queue.put(
            [
                self.unsafe_unpend_external_irq,
                False,  # increment_pc
                tuple(),
            ]
        )
        self.intr_queue.join()

    def queue_unsafe_pend_sysintr(self, intr: int) -> None:
        self.intr_queue.put(
            [
                self.unsafe_pend_sysintr,
                False,  # increment_pc
                (intr,),
            ]
        )
        self.intr_queue.join()

    def handle_externally_pended_interrupts(self) -> None:
        if not self.external_interrupt_pending.is_set():
            return
        self.external_interrupt_pending.clear()

        self.intr_queue.put(
            [
                None,
                False,  # increment_pc
                tuple(),
            ]
        )
        self.intr_queue.join()

    def should_autoclear_exception(self, exception_num: int) -> None:
        # NMI, HardFault, MemManage, BusFault, UsageFault, SVCall, DebugMonitor,
        # PendSV, SysTick
        if exception_num not in [2, 3, 4, 5, 6, 11, 12, 14, 15]:
            if exception_num not in _CUSTOM_AUTOUNPEND:
                return

        # Unpend the interrupt we're about to branch to.
        if exception_num >= 16:
            with self.nvic_pend_lock:
                self.nvic_pend[exception_num - 15 - 1] = False
        elif exception_num < 16:
            self.nvic_sys_pend[exception_num - 1] = False

    def pend_svcall_interrupt(self) -> None:
        curr_exc_pri = self.get_current_exception_priority()

        # We are in an exception, can we branch to SVCall?
        if curr_exc_pri != 0xFFFFFFFF:
            if self.nvic_sys_pri[11 - 1] >= curr_exc_pri:
                # Current exception priority is more important than SVCall!
                # HardFault!! We cannot skip the SVC instruction.
                self.nvic_sys_pend[3 - 1] = True
                return

        self.nvic_sys_pend[11 - 1] = True

    def pend_external_irq(self, irq) -> None:
        with self.nvic_pend_lock:
            self.nvic_pend[irq] = True
        self.external_interrupt_pending.set()

    def unpend_external_irq(self, irq) -> None:
        with self.nvic_pend_lock:
            self.nvic_pend[irq] = False
        self.external_interrupt_pending.set()

    def unsafe_pend_external_irq(self, irq) -> None:
        with self.nvic_pend_lock:
            self.nvic_pend[irq] = True

    def unsafe_unpend_external_irq(self, irq) -> None:
        with self.nvic_pend_lock:
            self.nvic_pend[irq] = False

    def unsafe_pend_sysintr(self, intr) -> None:
        self.nvic_sys_pend[intr - 1] = True

    def wait_for_interrupt(self) -> None:
        """
        The only thing that can wake the M3 up from sleep is an external
        interrupt that starts to pend. Therefore, wait until
        external_interrupt_pending is set.

        We should NOT interrupt here though, we should wait until it's safe to
        interrupt before interrupting. Let handle_externally_pended_interrupts
        handle it. The caller should be responsible to use UC_HOOK_BLOCK
        before calling it.
        """
        self.external_interrupt_pending.wait()
        return

    def exc_return_callback(self) -> None:
        address = self.ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_PC) | 1
        if address == _EXC_RETURN_VALS[0] or address == _EXC_RETURN_VALS[1]:
            sp_type = qemu.arm_const.UC_ARM_REG_MSP
        elif address == _EXC_RETURN_VALS[2]:
            sp_type = qemu.arm_const.UC_ARM_REG_PSP
        else:
            prints.fatal(f"EXC_RETURN invalid pc=0x{address:x}")

        if self.ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_IPSR) != 2:
            self.ctx.ucmutex.reg_write(qemu.arm_const.UC_ARM_REG_FAULTMASK, 0)

        for reg in reversed(
            [
                qemu.arm_const.UC_ARM_REG_XPSR,
                qemu.arm_const.UC_ARM_REG_PC,
                qemu.arm_const.UC_ARM_REG_LR,
                qemu.arm_const.UC_ARM_REG_R12,
                qemu.arm_const.UC_ARM_REG_R3,
                qemu.arm_const.UC_ARM_REG_R2,
                qemu.arm_const.UC_ARM_REG_R1,
                qemu.arm_const.UC_ARM_REG_R0,
            ]
        ):
            reg_val = read_u32_from_sp(self.ctx.ucmutex, sp_type)
            self.ctx.ucmutex.reg_write(reg, reg_val)

    def check_for_pending_exceptions(self, pending_exceptions: dict) -> None:
        # Populate pending_exceptions with pending exceptions.
        # exception_num: priority

        # Always check NMI/Reset, they can never be blocked.

        # Reset
        if self.nvic_sys_pend[0]:
            pending_exceptions[1] = self.nvic_sys_pri[0]

        # NMI
        if self.nvic_sys_pend[1]:
            pending_exceptions[2] = self.nvic_sys_pri[1]

        # FAULTMASK is set, all exceptions disabled NMI and Reset.
        if self.ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_FAULTMASK):
            return

        # HardFault
        if self.nvic_sys_pend[2]:
            pending_exceptions[3] = self.nvic_sys_pri[2]

        # PRIMASK is set, only allow Reset/NMI/HardFault.
        if self.ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_PRIMASK):
            return

        for exc in range(len(self.nvic_sys_pend)):
            if not self.nvic_sys_pend[exc]:
                continue
            pending_exceptions[exc + 1] = self.nvic_sys_pri[exc]

        with self.nvic_pend_lock:
            for irq in range(len(self.nvic_pend)):
                if not self.nvic_pend[irq]:
                    continue
                if not self.nvic_en[irq]:
                    continue
                pending_exceptions[irq + 16] = self.nvic_pri[irq]

    def get_current_exception_priority(self) -> bool:
        current_exc_num = self.ctx.uc.reg_read(qemu.arm_const.UC_ARM_REG_IPSR)

        if current_exc_num:
            # We are in an exception. Check it's priority level.
            if current_exc_num >= 16:
                return self.nvic_pri[current_exc_num - 16]
            else:
                return self.nvic_sys_pri[current_exc_num - 1]

        # Return an impossible exception priority, signifying that there's no
        # exception active, because it's impossible to get a priority.
        return 0xFFFFFFFF

    def should_trigger_exception(self, pending_exceptions: dict) -> int:
        # First, find a winning exception out of all the pending
        # exceptions.
        winning_exc = min(
            pending_exceptions.items(), key=lambda x: (x[1], x[0])
        )
        winning_exc_num, winning_exc_pri = winning_exc

        # Second, check if we are in an exception. If so, check its priority
        # level to see if it's lower than our winning_exc.
        current_exc_pri = self.get_current_exception_priority()
        if current_exc_pri != 0xFFFFFFFF:  # Means we're not in an exception.
            # In an exception.
            if winning_exc_pri >= current_exc_pri:
                # The current winning exception priority isn't low enough. Do
                # not trigger another stacked exception.
                return -1

        # We aren't in an exception, or the new exception won.
        return winning_exc_num

    def branch_to_exception(self, exception_num: int) -> None:
        # exception_num starts from 1 here.

        # We now have to branch to an exception handler.
        #
        # Within unicorn, we need to handle interrupts a little differently.
        # We use a queue context to check if we need to branch to an interrupt
        # for every M3 operation that may change a condition that allows
        # interrupting. This allows us to have extremely fast execution speed
        # as we do not need to check for a pending interrupt every instruction,
        # which detrimentally affects execution, expecially within Python.
        #
        # Therefore, we have a variable to define interrupt behavior.
        #
        # intr_ctx_pc_increment:
        # If the last operation to change a condition within the M3 was from an
        # internally triggered mem write, which is to say writing to the STIR
        # register, then the emulator has already stopped running. We can just
        # modify emulator state directly. The issue is that the PC has not been
        # advanced yet. Therefore, from our current PC, we need to calculate our
        # current instruction's PC, then advance the PC past it. After which,
        # we are able to modify emulator state easily to handle an exception
        # and save our exception frame to the stack.

        ret_pc = self.ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_PC)

        # Using a ARM instruction opcode hack, find the next pc.
        if self.intr_ctx_increment_pc:
            ret_pc += armv7m_find_instruction_size(self.ctx.ucmutex, ret_pc)

        self.ctx.ucmutex.reg_write(qemu.arm_const.UC_ARM_REG_PC, ret_pc | 1)

        # Build the EXC_RETURN value based on IPSR and current SP.
        current_mode = None
        current_sp = None
        built_exc_return = None
        if (
            self.ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_CONTROL) & 2
        ):  # thread = psp, handler = msp
            if self.ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_IPSR):
                # handler
                current_mode = "handler"
                current_sp = "msp"
            else:
                # thread
                current_mode = "thread"
                current_sp = "psp"
        else:  # thread = msp, handler = msp
            if self.ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_IPSR):
                # handler
                current_mode = "handler"
            else:
                # thread
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

        # Push the exception frame to the stack
        for reg in [
            qemu.arm_const.UC_ARM_REG_XPSR,
            qemu.arm_const.UC_ARM_REG_PC,
            qemu.arm_const.UC_ARM_REG_LR,
            qemu.arm_const.UC_ARM_REG_R12,
            qemu.arm_const.UC_ARM_REG_R3,
            qemu.arm_const.UC_ARM_REG_R2,
            qemu.arm_const.UC_ARM_REG_R1,
            qemu.arm_const.UC_ARM_REG_R0,
        ]:
            reg_val = self.ctx.ucmutex.reg_read(reg)
            if reg == qemu.arm_const.UC_ARM_REG_PC:
                reg_val |= 1
            write_u32_to_sp(self.ctx.ucmutex, reg_val)

        # Place EXC_RETURN val into LR and enter handler mode by changing IPSR.
        self.ctx.ucmutex.reg_write(
            qemu.arm_const.UC_ARM_REG_LR, built_exc_return
        )
        self.ctx.ucmutex.reg_write(
            qemu.arm_const.UC_ARM_REG_IPSR, exception_num
        )

        # IT state is cleared, as documented in the ARM psuedocode
        # EPSR.IT<7:0> = Zeros(8);
        self.ctx.ucmutex.reg_write(
            qemu.arm_const.UC_ARM_REG_EPSR,
            (
                self.ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_EPSR)
                & ~0x600FC00
            ),
        )

        # Generate the handler's PC based on the VTOR address
        # VTOR addr + Exception * 4
        exception_pc = self.ctx.ucmutex.int32_mem_read(
            self.cpu.vtor + ((exception_num) * 4)
        )
        self.ctx.ucmutex.reg_write(qemu.arm_const.UC_ARM_REG_PC, exception_pc)

        # print(
        #     f"branching to {exception_num} at pc={exception_pc:x}, "+
        #     f"retpc={ret_pc:x}"
        # )

        # If the NVIC should handle this exception pend clear, do it.
        self.should_autoclear_exception(exception_num)

    def read_iser(self, size: int, queue: queue.Queue, index: int) -> None:
        value = 0
        base = index * 32
        for bit in range(32):
            if self.nvic_en[base + bit]:
                value |= 1 << bit
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
                value |= 1 << bit
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
                value |= 1 << bit
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
                value |= 1 << bit
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
            value |= ((self.nvic_pri[base + byte] & 0x7) << 5) << (byte * 8)

        queue.put(value)

    def write_ipr(self, size: int, value: int, index: int) -> None:
        base = index * 4
        for byte in range(4):
            self.nvic_pri[base + byte] = (
                ((value >> (byte * 8)) & 0xFF) >> 5
            ) & 0x7

    def read_stir(self, size: int, queue: queue.Queue) -> None:
        unhandled_register_io(prints, "READ", "NVIC_STIR", "M3")
        queue.put(0)

    def write_stir(self, size: int, value: int) -> None:
        # 0x1FF as of ARM spec which states that bits 9 - 32 are reserved.
        self.nvic_pend[value & 0x1FF] = True


class ArmSC300:
    def __init__(self, ctx: EmulatorContext):
        self.ctx = ctx

        self.mutex = FifoLock()
        self.cpuid = 0x410FC331  # Known CPUID for the ArmSC300

        self.intr_op = ArmInterruptHandler(self)
        self.intr_op.start_intr_worker()

        self.cyccnt_time_start = 0
        self.itcmcr = 0
        self.demcr = 0
        self.shscr = 0
        self.ccr = 0
        self.dwt_ctrl = 0
        self.vtor = 0

        # Extra debug registers
        self.mmfs = 0
        self.bfar = 0
        self.mfar = 0
        self.hfsr = 0
        self.dfsr = 0

    def start_cyccnt_time(self) -> None:
        with self.mutex:
            self.cyccnt_time_start = time.perf_counter_ns()

    def read_mmfs(self, size: int) -> None:
        with self.mutex:
            return self.mmfs

    def write_mmfs(self, size: int, value: int) -> None:
        with self.mutex:
            self.mmfs = value

    def read_bfar(self, size: int) -> None:
        with self.mutex:
            return self.bfar

    def write_bfar(self, size: int, value: int) -> None:
        with self.mutex:
            self.bfar = value

    def read_mfar(self, size: int) -> None:
        with self.mutex:
            return self.mfar

    def write_mfar(self, size: int, value: int) -> None:
        with self.mutex:
            self.mfar = value

    def read_hfsr(self, size: int) -> None:
        with self.mutex:
            return self.hfsr

    def write_hfsr(self, size: int, value: int) -> None:
        with self.mutex:
            self.hfsr = value

    def read_dfsr(self, size: int) -> None:
        with self.mutex:
            return self.dfsr

    def write_dfsr(self, size: int, value: int) -> None:
        with self.mutex:
            self.dfsr = value

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


def init_ArmSC300(ctx: EmulatorContext, regs: dict):
    c_emu = ArmSC300(ctx)

    reg_fn_map = {
        regs["DEMCR"]: [c_emu.read_demcr, c_emu.write_demcr],
        regs["DWT_CTRL"]: [c_emu.read_dwt_ctrl, c_emu.write_dwt_ctrl],
        regs["CPUID"]: [c_emu.read_cpuid, c_emu.write_cpuid],
        regs["ITCMCR"]: [c_emu.read_itcmcr, c_emu.write_itcmcr],
        regs["DWT_CYCCNT"]: [c_emu.read_dwt_cyccnt, c_emu.write_dwt_cyccnt],
        regs["VTOR"]: [c_emu.read_vtor, c_emu.write_vtor],
        regs["CCR"]: [c_emu.read_ccr, c_emu.write_ccr],
        regs["SHSCR"]: [c_emu.read_shscr, c_emu.write_shscr],
        regs["MMFS"]: [c_emu.read_mmfs, c_emu.write_mmfs],
        regs["BFAR"]: [c_emu.read_bfar, c_emu.write_bfar],
        regs["MFAR"]: [c_emu.read_mfar, c_emu.write_mfar],
        regs["HFSR"]: [c_emu.read_hfsr, c_emu.write_hfsr],
        regs["DFSR"]: [c_emu.read_dfsr, c_emu.write_dfsr],
    }

    intr_fn_map = {
        regs["NVIC_STIR"]: [c_emu.intr_op.read_stir, c_emu.intr_op.write_stir]
    }

    idx_regs_to_regmap(
        intr_fn_map,
        regs["NVIC_ISER"],
        c_emu.intr_op.read_iser,
        c_emu.intr_op.write_iser,
    )

    idx_regs_to_regmap(
        intr_fn_map,
        regs["NVIC_ICER"],
        c_emu.intr_op.read_icer,
        c_emu.intr_op.write_icer,
    )

    idx_regs_to_regmap(
        intr_fn_map,
        regs["NVIC_ICPR"],
        c_emu.intr_op.read_icpr,
        c_emu.intr_op.write_icpr,
    )

    idx_regs_to_regmap(
        intr_fn_map,
        regs["NVIC_IPR"],
        c_emu.intr_op.read_ipr,
        c_emu.intr_op.write_ipr,
    )

    for k, v in intr_fn_map.items():
        reg_fn_map[k] = [
            args_lambda_gen(c_emu.intr_op.queue_internal_read_worker_op, v[0]),
            args_lambda_gen(c_emu.intr_op.queue_internal_write_worker_op, v[1]),
        ]

    def component_read_handler(
        uc: qemu.Uc, offset: int, size: int, user_data: typing.Any
    ) -> int:
        try:
            return reg_fn_map[offset][0](size)
        except KeyError:
            unhandled_register_exit(ctx, prints, "M3", offset)

    def component_write_handler(
        uc: qemu.Uc, offset: int, size: int, value: int, user_data: typing.Any
    ) -> None:
        try:
            reg_fn_map[offset][1](size, value)
        except KeyError:
            unhandled_register_exit(ctx, prints, "M3", offset)

    return ComponentObjects(
        c_emu, component_read_handler, component_write_handler
    )


def exc_return_handler(c_emu: ArmSC300) -> None:
    c_emu.intr_op.queue_exc_return()


def unsafe_pend_external_irq(c_emu: ArmSC300, irq: int) -> None:
    # Only use this if we are sure that it is run in a single threaded
    # context(must be synchronous, not asynchronous with emulator)
    c_emu.intr_op.queue_unsafe_pend_external_irq(irq)


def unsafe_unpend_external_irq(c_emu: ArmSC300, irq: int) -> None:
    # Only use this if we are sure that it is run in a single threaded
    # context(must be synchronous, not asynchronous with emulator)
    c_emu.intr_op.queue_unsafe_unpend_external_irq(irq)


def unsafe_pend_sysintr(c_emu: ArmSC300, intr: int) -> None:
    # Only use this if we are sure that it is run in a single threaded
    # context(must be synchronous, not asynchronous with emulator)
    c_emu.intr_op.queue_unsafe_pend_sysintr(intr)


def pend_external_irq(c_emu: ArmSC300, irq: int) -> None:
    c_emu.intr_op.pend_external_irq(irq)


def unpend_external_irq(c_emu: ArmSC300, irq: int) -> None:
    c_emu.intr_op.unpend_external_irq(irq)


def pend_svcall_interrupt(c_emu: ArmSC300) -> None:
    c_emu.intr_op.queue_svcall_interrupt()


def handle_externally_pended_interrupts(c_emu: ArmSC300) -> None:
    c_emu.intr_op.handle_externally_pended_interrupts()


def wait_for_interrupt(c_emu: ArmSC300) -> None:
    c_emu.intr_op.wait_for_interrupt()
