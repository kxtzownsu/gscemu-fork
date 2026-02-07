# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import typing
import unicorn as qemu
import queue
import threading
import time

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from ..registers import FLASH_REGS
from lib.helpers import (
    unhandled_register_exit, 
    unhandled_register_io, 
    idx_regs_to_regmap
)

# flash mappings:
# bank0, control0 = RO_A + RW_A (0x40000 - 0x7ffff) -> flash bank(0x0 - 0x3ffff)
# bank0, control1 = RO_B + RW_B (0x80000 - 0xbffff) -> flash bank(0x0 - 0x3ffff)
# bank1, control0 = should exist, but never used. do not support.
# bank1, control1 = INFO1       (0x28000 - 0x287ff) -> flash bank(0x0 - 0x7ff)

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

_FSH_START_ADDR_MAP = [
    [0x40000, 0x80000],
    [None, 0x28000]
]
_FSH_SIZE_BOUNDS = [
    0x3ffff, # BANK0 bounds
    0x7ff # BANK1 bounds
]
_FSH_PE_EN_MAGIC = 0xb11924e1
_FSH_OP_ERASE_BLOCK = 0x31415927
_FSH_OP_WRITE_BLOCK = 0x27182818
_FSH_OP_READ_BLOCK = 0x16021765
_FSH_OP_BULK_ERASE_BANK = 0x1d1e2bad

class FlashController:
    def __init__(self):
        self.opqueue = queue.Queue()
        self.opworker = None

        # appleflyer: We need a better way to handle this, but for now this will 
        # do.
        self.opmap = {
            _FSH_OP_READ_BLOCK: self.op_read_block,
            _FSH_OP_WRITE_BLOCK: self.op_write_block,
            _FSH_OP_ERASE_BLOCK: self.op_erase_block,
            _FSH_OP_BULK_ERASE_BANK: self.op_bulk_erase_bank,
        }

        # Used to enable the TSMC proprietary smart algorithms for prog/erase?
        # Doesn't matter to us, this is an emulator.
        self.timing_prog_smart_algo = True
        self.timing_erase_smart_algo = True
        self.timing_bulkerase_smart_algo = True

        self.error_placed_time = None
        self.error_code = 0

        # If this has the correct magic value, we can kick off an operation.
        self.pe_en = 0

        self.opcode = 0
        self.pe_control = 0 # Helps us know which CONTROL side to use.

        self.trans_offset = 0
        self.trans_mainb = 0
        self.trans_size = 0

        self.dout_val = [0] * 2
        self.wr_data = [0] * 32
        self.protect_info1_erase = 0

        # Temporary variables used during ops.
        self.start_addr = 0

    def flash_worker(self):
        while True:
            try:
                # Wait for the next operation to enter the queue
                target_fn, args = self.opqueue.get()

                # If an error_code exists, we need to clear it after a certain
                # period of time.
                if self.error_code:
                    self.should_clear_error()

                target_fn(*args) # Splat the arguments into the target_fn

                # For write operations, this doesn't do anything. For read
                # operations, we need to tell the handler that we have processed
                # the value, and execution can proceed.
                self.opqueue.task_done()

                if not self.pe_control:
                    # We did not recieve any opcode, which means the system
                    # hasn't requested a FLASH operation yet.
                    continue
                
                self.start_addr = (
                    _FSH_START_ADDR_MAP[self.trans_mainb][self.pe_control]
                )

                if not self.start_addr:
                    # On the Cr50, INFO0 is never used. Therefore, we will also
                    # not allow usage of it. We also do not know where INFO0 is
                    # mapped, or if it is even mapped.
                    prints.warning("BANK1, CONTROL0 used, unsupported config.")
                else:
                    try:
                        self.opmap[self.opcode]()
                    except KeyError:
                        prints.warning("Invalid PE_CONTROL provided to FLASH!")

                # Operation completed! Clear the PE_CONTROL variable and PE_EN.
                self.pe_control = 0
                self.pe_en = 0

                # Let's clear the temporary variables too.
                self.start_addr = 0

                # Start the error_code clear countdown if there was an error.
                self.error_countdown()

            except Exception as e:
                prints.fatal(e)

    def start_worker(self):
        if not self.opworker:
            self.opworker = threading.Thread(target=self.flash_worker)
            self.opworker.daemon = True
            self.opworker.start()

    def queue_read_worker_op(self, size: int, target_fn):
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()
        
    def queue_write_worker_op(self, size: int, value: int, target_fn):
        self.opqueue.put([target_fn, (size, value)])

    def op_erase_block(self):
        # Check if INFO1 is erase locked.
        if self.protect_info1_erase:
            if (self.trans_mainb == 1 
                and self.pe_control == 1):
                # BIT(7) | BIT(12), erase_failed | info1_erase_locked
                self.error_code |= (128 | 4096)
                return
        
        # Check if the TRANS_OFFSET is page aligned.
        if self.trans_offset % 0x200:
            # BIT(7) | BIT(4), erase_failed | erase_not_page_aligned
            self.error_code |= (128 | 16)
            return
        
        # Check if our TRANS_OFFSET is within bounds.
        self.start_addr = self.start_addr + (self.trans_offset * 4)
        if self.start_addr > _FSH_SIZE_BOUNDS[self.trans_mainb]:
            if self.trans_mainb == 0:
                self.error_code |= 2 # BIT(1), out_of_main_range
            elif self.trans_mainb == 1:
                self.error_code |= 4 # BIT(2), out_of_info_range
            return
        
        # All checks passed, start OP_ERASE.
        ucmutex().mem_write(self.start_addr, b'\xff' * 0x800)

    def op_write_block(self):
        # Every write must be aligned to the row boundary.
        if (
            (self.trans_offset // 64) != 
            ((self.trans_offset + self.trans_size) // 64)
        ):
            # Write was not aligned to row boundary!
            self.error_code |= 1 # BIT(0), prog_not_row_aligned

        self.start_addr = self.start_addr + (self.trans_offset * 4)

        # Count register is zero-based, according to Cr50 source. Therefore, we
        # need to increment TRANS_SIZE by 1.
        for word in range(0, self.trans_size + 1):
            ucmutex().int32_mem_write(
                self.start_addr + (word * 4),
                self.wr_data[word]
            )

    def op_read_block(self):
        # We need to ensure the system is only asking for one u32. Anything more
        # or less is invalid.
        if self.trans_size != 1:
            self.error_code |= 8192 # BIT(13), access_invalid_flash0
            return
        
        self.start_addr = self.start_addr + (self.trans_offset * 4)
        
        self.dout_val[self.pe_control] = (
            ucmutex().int32_mem_read(self.start_addr)
        )

    def op_bulk_erase_bank(self):
        # Nothing much to check, because most of the values aren't used.
        
        if self.trans_mainb == 0:
            ucmutex().mem_write(self.start_addr, b'\xff' * 0x40000)

        elif self.trans_mainb == 1:
            if self.protect_info1_erase:
                self.error_code |= 128 # BIT(7), erase_failed
                return
            
            ucmutex().mem_write(self.start_addr, b'\xff' * 0x800)

    def should_clear_error(self):
        # Should we clear the error_code?

        if self.error_placed_time is None: # Honestly this shouldn't resolve.
            # If this condition resolves, it means error_code is non-zero, but
            # there was no timer set. We should just clear the error_code. This
            # is developer negligence.
            self.error_code = 0
            prints.warning("FLASH ERROR register invalid state!")
        
        # Give 5ms of time before clearing the error.
        if time.perf_counter() > (self.error_placed_time + 0.005):
            prints.debug("FLASH cleared error_code!")
            self.error_placed_time = None
            self.error_code = 0

    def error_countdown(self):
        # If we have an error code, we need to start the countdown.
        if self.error_code:
            if self.error_placed_time:
                return
            self.error_placed_time = time.perf_counter()

    def read_pe_control_0(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.pe_control)

    def write_pe_control_0(self, size: int, value: int) -> None:
        # We do not need to handle the case of another write changing the opcode
        # and PE_CONTROL values. On this write, the queue cycle would
        # immediately process it already. Subsequent writes will see a cleared
        # opcode and PE_CONTROL.

        # Ignore the PE_CONTROL write if PE_EN does not match the magic.
        if self.pe_en != _FSH_PE_EN_MAGIC:
            return
        
        self.opcode = value
        self.pe_control = 0

    def read_pe_control_1(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.pe_control)

    def write_pe_control_1(self, size: int, value: int) -> None:
        # We do not need to handle the case of another write changing the opcode
        # and PE_CONTROL values. On this write, the queue cycle would
        # immediately process it already. Subsequent writes will see a cleared
        # opcode and PE_CONTROL.

        # Ignore the PE_CONTROL write if PE_EN does not match the magic.
        if self.pe_en != _FSH_PE_EN_MAGIC:
            return
        
        self.opcode = value
        self.pe_control = 1

    def read_pe_en(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.pe_en)

    def write_pe_en(self, size: int, value: int) -> None:
        self.pe_en = value

    def read_trans(self, size: int, queue: queue.Queue) -> None:
        val = (
            self.trans_offset |
            (self.trans_mainb << 16) |
            (self.trans_size << 17)
        )
        queue.put(val)

    def write_trans(self, size: int, value: int) -> None:
        self.trans_offset = value & 0xffff
        self.trans_mainb = (value & 0x10000) >> 16
        self.trans_size = ((value & 0x3e0000) >> 17)

    def read_error(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.error_code)

    def write_error(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "FLASH0", "FSH_ERROR")

    def read_protect_info1_erase(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.protect_info1_erase)

    def write_protect_info1_erase(self, size: int, value: int) -> None:
        # TODO(appleflyer): Should we allow PROTECT_INFO1_ERASE disabling? Test
        # with RMASmoke
        if not self.protect_info1_erase:
            self.protect_info1_erase = value

    def read_dout_val0(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.dout_val[0])

    def write_dout_val0(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "FLASH0", "DOUT_VAL0")

    def read_dout_val1(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.dout_val[1])

    def write_dout_val1(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "FLASH0", "DOUT_VAL1")

    def read_wr_data(self, size: int, queue: queue.Queue, index: int) -> None:
        queue.put(self.wr_data[index])

    def write_wr_data(self, size: int, value: int, index: int) -> None:
        self.wr_data[index] = value

    def read_prog_smart_algo(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.timing_prog_smart_algo)

    def write_prog_smart_algo(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "FLASH0", "PROG_SMART_ALGO")

    def read_erase_smart_algo(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.timing_erase_smart_algo)

    def write_erase_smart_algo(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "FLASH0", "ERASE_SMART_ALGO")

    def read_bulkerase_smart_algo(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.timing_bulkerase_smart_algo)

    def write_bulkerase_smart_algo(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "FLASH0", "BULKERASE_SMART_ALGO")

c_emu = FlashController()
c_emu.start_worker()

_REG_FUNC_MAP = {
    FLASH_REGS["PE_CONTROL0"]: [
        c_emu.read_pe_control_0, c_emu.write_pe_control_0
    ],
    FLASH_REGS["PE_CONTROL1"]: [
        c_emu.read_pe_control_1, c_emu.write_pe_control_1
    ],
    FLASH_REGS["PE_EN"]: [
        c_emu.read_pe_en, c_emu.write_pe_en
    ],
    FLASH_REGS["TRANS"]: [
        c_emu.read_trans, c_emu.write_trans
    ],
    FLASH_REGS["ERROR"]: [
        c_emu.read_error, c_emu.write_error
    ],
    FLASH_REGS["PROTECT_INFO1_ERASE"]: [
        c_emu.read_protect_info1_erase, c_emu.write_protect_info1_erase
    ],
    FLASH_REGS["DOUT_VAL0"]: [
        c_emu.read_dout_val0, c_emu.write_dout_val0
    ],
    FLASH_REGS["DOUT_VAL1"]: [
        c_emu.read_dout_val1, c_emu.write_dout_val1
    ],
    FLASH_REGS["PROG_SMART_ALGO"]: [
        c_emu.read_prog_smart_algo, c_emu.write_prog_smart_algo,
    ],
    FLASH_REGS["ERASE_SMART_ALGO"]: [
        c_emu.read_erase_smart_algo, c_emu.write_erase_smart_algo,
    ],
    FLASH_REGS["BULKERASE_SMART_ALGO"]: [
        c_emu.read_bulkerase_smart_algo, c_emu.write_bulkerase_smart_algo,
    ],
}

idx_regs_to_regmap(
    _REG_FUNC_MAP, FLASH_REGS["WR_DATA"], 
    c_emu.read_wr_data, c_emu.write_wr_data
)

def component_read_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    user_data: typing.Any,
) -> int:
    try:
        return c_emu.queue_read_worker_op(size, _REG_FUNC_MAP[offset][0])
    except KeyError:
        unhandled_register_exit(g_uc(), ucthread(), prints, "FLASH0", offset)

def component_write_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    value: int,
    user_data: typing.Any,
) -> None:
    try:
        c_emu.queue_write_worker_op(size, value, _REG_FUNC_MAP[offset][1])
    except KeyError:
        unhandled_register_exit(g_uc(), ucthread(), prints, "FLASH0", offset)