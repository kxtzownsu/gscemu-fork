# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import typing
import unicorn as qemu
import queue
import threading

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from .regdefs import PMU_REGS
from lib.helpers import (
    unhandled_register_exit, 
    unhandled_register_io,
    idx_regs_to_regmap
)

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

class PowerManagementUnit:
    def __init__(self):
        self.opthread = None
        self.opqueue = queue.Queue()

        self.rstsrc = 0
        self.int_enable = False

        self.low_power_seq = 0
        self.exitpd_mask = 0

        self.sw_pdb = 0
        self.periph_clocks_en = [False] * 48

        self.chip_id = {
            "JTAG_STANDARD": 0x1, # bit 0
            "MFG_ID": 0x4a6, # bits 1-11
            "PART_NUM": 0x4856, # bits 12-27
            "REVISION": 4, # bits 28-31
        }

        self.pwrdn_scratch = [0] * 32
        self.pwrdn_scratch_lock = [0] * 2

        self.long_life_scratch = [0] * 4
        # Enabled or disabled by default?
        self.long_life_scratch_wr_en = [True] * 4

        # Enabled or disabled by default?
        self.rst_wr_en = [True] * 2

    def pmu_worker(self):
        while True:
            try:
                op = self.opqueue.get()
                target_fn, args = op

                target_fn(*args)

                self.opqueue.task_done()

            except Exception as e:
                prints.fatal(e)

    def start_worker(self):
        if not self.opthread:
            self.opthread = threading.Thread(target=self.pmu_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn):
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()
        
    def queue_write_worker_op(self, size: int, value: int, target_fn):
        self.opqueue.put([target_fn, (size, value)])

    def read_periclkset0(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(32):
            if self.periph_clocks_en[bit]:
                val |= (1 << bit)

        queue.put(val)
    
    def write_periclkset0(self, size: int, value: int):
        for bit in range(32):
            if self.periph_clocks_en[bit]:
                continue
            
            if value & (1 << bit):
                self.periph_clocks_en[bit] = True

    def read_periclkclr0(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(32):
            if self.periph_clocks_en[bit]:
                val |= (1 << bit)

        queue.put(val)
    
    def write_periclkclr0(self, size: int, value: int):
        for bit in range(32):
            if not self.periph_clocks_en[bit]:
                continue
            
            if value & (1 << bit):
                self.periph_clocks_en[bit] = False

    def read_periclkset1(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            if self.periph_clocks_en[bit+32]:
                val |= (1 << bit)

        queue.put(val)

    def write_periclkset1(self, size: int, value: int):
        for bit in range(16):
            if self.periph_clocks_en[bit+32]:
                continue
            
            if value & (1 << bit):
                self.periph_clocks_en[bit+32] = True

    def read_periclkclr1(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            if self.periph_clocks_en[bit+32]:
                val |= (1 << bit)

        queue.put(val)
    
    def write_periclkclr1(self, size: int, value: int):
        for bit in range(16):
            if not self.periph_clocks_en[bit+32]:
                continue
            
            if value & (1 << bit):
                self.periph_clocks_en[bit+32] = False

    def read_chip_id(self, size: int, queue: queue.Queue):
        val = 0
        val |= (self.chip_id["JTAG_STANDARD"] & 0x1)
        val |= (self.chip_id["MFG_ID"] & 0x7FF) << 1
        val |= (self.chip_id["PART_NUM"] & 0xFFFF) << 12
        val |= (self.chip_id["REVISION"] & 0xF) << 28

        queue.put(val)
    
    def write_chip_id(self, size: int, value: int):
        unhandled_register_io(prints, "WRITE", "PMU", "CHIP_ID")

    def read_low_power_dis(self, size: int, queue: queue.Queue):
        queue.put(self.low_power_seq)
    
    def write_low_power_dis(self, size: int, value: int):
        self.low_power_seq = value

    def read_exitpd_mask(self, size: int, queue: queue.Queue):
        queue.put(self.exitpd_mask)
    
    def write_exitpd_mask(self, size: int, value: int):
        self.exitpd_mask = value

    def read_sw_pdb(self, size: int, queue: queue.Queue):
        queue.put(self.sw_pdb)
    
    def write_sw_pdb(self, size: int, value: int):
        self.sw_pdb = value

    def read_int_enable(self, size: int, queue: queue.Queue):
        queue.put(int(self.int_enable))
    
    def write_int_enable(self, size: int, value: int):
        self.int_enable = bool(value)

    def read_pwrdn_scratch(self, size: int, queue: queue.Queue, index: int):
        queue.put(self.pwrdn_scratch[index])

    def write_pwrdn_scratch(self, size: int, value: int, index: int):
        if 0 <= index <= 7:
            if self.pwrdn_scratch_lock[0]:
                return
            
        elif 8 <= index <= 15:
            if self.pwrdn_scratch_lock[1]:
                return
            
        self.pwrdn_scratch[index] = value

    def read_pwrdn_scratch_lock(
            self, size: int, queue: queue.Queue, index: int
        ):
        queue.put(int(self.pwrdn_scratch_lock[index]))

    def write_pwrdn_scratch_lock(self, size: int, value: int, index: int):
        if value:
            self.pwrdn_scratch_lock[index] = True

    def read_rstsrc(self, size: int, queue: queue.Queue):
        queue.put(self.rstsrc)

    def write_rstsrc(self, size: int, value: int):
        unhandled_register_io(prints, "WRITE", "PMU", "RSTSRC")

    def read_clrrst(self, size: int, queue: queue.Queue):
        unhandled_register_io(prints, "READ", "PMU", "CLRRST")
        queue.put(0)

    def write_clrrst(self, size: int, value: int):
        if value:
            self.rstsrc = 0

    def read_rst(self, size: int, queue: queue.Queue, index: int):
        queue.put(0)

    def write_rst(self, size: int, value: int, index: int):
        # Implement component resetting.
        if self.rst_wr_en[index]:
            # Reset here
            pass

        return
    
    def read_rst_wr_en(self, size: int, queue: queue.Queue, index: int):
        queue.put(int(self.rst_wr_en[index]))

    def write_rst_wr_en(self, size: int, value: int, index: int):
        self.rst_wr_en[index] = bool(value)

    def read_long_life_scratch(self, size: int, queue: queue.Queue, index: int):
        queue.put(self.long_life_scratch[index])

    def write_long_life_scratch(self, size: int, value: int, index: int):
        if self.long_life_scratch_wr_en[index]:
            self.long_life_scratch[index] = value

    def read_long_life_scratch_wr_en(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(4):
            if self.long_life_scratch_wr_en[bit]:
                val |= (1 << bit)

        queue.put(val)

    def write_long_life_scratch_wr_en(self, size: int, value: int):
        for bit in range(4):
            if value & (1 << bit):
                self.long_life_scratch_wr_en[bit] = True
            else:
                self.long_life_scratch_wr_en[bit] = False

c_emu = PowerManagementUnit()
c_emu.start_worker()

_REG_FUNC_MAP = {
    PMU_REGS["CHIP_ID"]: [c_emu.read_chip_id, c_emu.write_chip_id],
    PMU_REGS["SW_PDB"]: [c_emu.read_sw_pdb, c_emu.write_sw_pdb],
    PMU_REGS["INT_ENABLE"]: [c_emu.read_int_enable, c_emu.write_int_enable],

    PMU_REGS["EXITPD_MASK"]: [c_emu.read_exitpd_mask, c_emu.write_exitpd_mask],
    PMU_REGS["LOW_POWER_DIS"]: [
        c_emu.read_low_power_dis, c_emu.write_low_power_dis
    ],

    PMU_REGS["PERICLKSET0"]: [c_emu.read_periclkset0, c_emu.write_periclkset0],
    PMU_REGS["PERICLKCLR0"]: [c_emu.read_periclkclr0, c_emu.write_periclkclr0],
    PMU_REGS["PERICLKSET1"]: [c_emu.read_periclkset1, c_emu.write_periclkset1],
    PMU_REGS["PERICLKCLR1"]: [c_emu.read_periclkclr1, c_emu.write_periclkclr1],

    PMU_REGS["CLRRST"]: [c_emu.read_clrrst, c_emu.write_clrrst],
    PMU_REGS["RSTSRC"]: [c_emu.read_rstsrc, c_emu.write_rstsrc],

    PMU_REGS["LONG_LIFE_SCRATCH_WR_EN"]: [
        c_emu.read_long_life_scratch_wr_en, c_emu.write_long_life_scratch_wr_en
    ],
}

idx_regs_to_regmap(
    _REG_FUNC_MAP, PMU_REGS["LONG_LIFE_SCRATCH"],
    c_emu.read_long_life_scratch, c_emu.write_long_life_scratch
)

idx_regs_to_regmap(
    _REG_FUNC_MAP, PMU_REGS["PWRDN_SCRATCH"],
    c_emu.read_pwrdn_scratch, c_emu.write_pwrdn_scratch
)

idx_regs_to_regmap(
    _REG_FUNC_MAP, PMU_REGS["PWRDN_SCRATCH_LOCK"],
    c_emu.read_pwrdn_scratch_lock, c_emu.write_pwrdn_scratch_lock
)

idx_regs_to_regmap(
    _REG_FUNC_MAP, PMU_REGS["RST_WR_EN"],
    c_emu.read_rst_wr_en, c_emu.write_rst_wr_en
)

idx_regs_to_regmap(
    _REG_FUNC_MAP, PMU_REGS["RST"],
    c_emu.read_rst, c_emu.write_rst
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
        unhandled_register_exit(g_uc(), ucthread(), prints, "PMU", offset)
        return 0

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
        unhandled_register_exit(g_uc(), ucthread(), prints, "PMU", offset)