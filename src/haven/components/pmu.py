# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

import queue
import threading
import typing

import unicorn as qemu

from env import *
from lib.emulator_context import ComponentObjects, EmulatorContext
from lib.helpers import (
    idx_regs_to_regmap,
    unhandled_register_exit,
    unhandled_register_io,
)
from lib.logger import GscemuLogger

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


class PowerManagementUnit:
    def __init__(self, ctx: EmulatorContext):
        self.ctx = ctx

        self.opthread = None
        self.opqueue = queue.Queue()

        self.rstsrc = 0
        self.int_enable = False

        self.low_power_seq = 0
        self.exitpd_mask = 0

        self.sw_pdb = 0
        self.periph_clocks_en = [False] * 48

        # REVISION:
        # 3 -> B1
        # 4 -> B2
        self.chip_id = {
            "JTAG_STANDARD": 0x1,  # bit 0
            "MFG_ID": 0x4A6,  # bits 1-11
            "PART_NUM": 0x4856,  # bits 12-27
            "REVISION": 4,  # bits 28-31
        }

        self.pwrdn_scratch = [0] * 32
        self.pwrdn_scratch_lock = [0] * 2

        self.long_life_scratch = [0] * 4
        # Enabled or disabled by default?
        self.long_life_scratch_wr_en = [True] * 4

        # Enabled or disabled by default?
        self.rst_wr_en = [True] * 2

    def pmu_worker(self) -> None:
        while True:
            try:
                op = self.opqueue.get()
                target_fn, args = op

                target_fn(*args)

                self.opqueue.task_done()

            except Exception as e:
                prints.fatal(e)

    def start_worker(self) -> None:
        if not self.opthread:
            self.opthread = threading.Thread(target=self.pmu_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn) -> int:
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()

    def queue_write_worker_op(self, size: int, value: int, target_fn) -> None:
        self.opqueue.put([target_fn, (size, value)])

    def read_periclkset0(self, size: int, queue: queue.Queue) -> None:
        val = 0
        for bit in range(32):
            if self.periph_clocks_en[bit]:
                val |= 1 << bit

        queue.put(val)

    def write_periclkset0(self, size: int, value: int) -> None:
        for bit in range(32):
            if self.periph_clocks_en[bit]:
                continue

            if value & (1 << bit):
                self.periph_clocks_en[bit] = True

    def read_periclkclr0(self, size: int, queue: queue.Queue) -> None:
        val = 0
        for bit in range(32):
            if self.periph_clocks_en[bit]:
                val |= 1 << bit

        queue.put(val)

    def write_periclkclr0(self, size: int, value: int) -> None:
        for bit in range(32):
            if not self.periph_clocks_en[bit]:
                continue

            if value & (1 << bit):
                self.periph_clocks_en[bit] = False

    def read_periclkset1(self, size: int, queue: queue.Queue) -> None:
        val = 0
        for bit in range(16):
            if self.periph_clocks_en[bit + 32]:
                val |= 1 << bit

        queue.put(val)

    def write_periclkset1(self, size: int, value: int) -> None:
        for bit in range(16):
            if self.periph_clocks_en[bit + 32]:
                continue

            if value & (1 << bit):
                self.periph_clocks_en[bit + 32] = True

    def read_periclkclr1(self, size: int, queue: queue.Queue) -> None:
        val = 0
        for bit in range(16):
            if self.periph_clocks_en[bit + 32]:
                val |= 1 << bit

        queue.put(val)

    def write_periclkclr1(self, size: int, value: int) -> None:
        for bit in range(16):
            if not self.periph_clocks_en[bit + 32]:
                continue

            if value & (1 << bit):
                self.periph_clocks_en[bit + 32] = False

    def read_chip_id(self, size: int, queue: queue.Queue) -> None:
        val = 0
        val |= self.chip_id["JTAG_STANDARD"] & 0x1
        val |= (self.chip_id["MFG_ID"] << 1) & 0xFFE
        val |= (self.chip_id["PART_NUM"] << 12) & 0xFFFF000
        val |= (self.chip_id["REVISION"] << 28) & 0xF0000000

        queue.put(val)

    def write_chip_id(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "PMU", "CHIP_ID")

    def read_low_power_dis(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.low_power_seq)

    def write_low_power_dis(self, size: int, value: int) -> None:
        self.low_power_seq = value

    def read_exitpd_mask(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.exitpd_mask)

    def write_exitpd_mask(self, size: int, value: int) -> None:
        self.exitpd_mask = value

    def read_sw_pdb(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.sw_pdb)

    def write_sw_pdb(self, size: int, value: int) -> None:
        self.sw_pdb = value

    def read_int_enable(self, size: int, queue: queue.Queue) -> None:
        queue.put(int(self.int_enable))

    def write_int_enable(self, size: int, value: int) -> None:
        self.int_enable = bool(value)

    def read_pwrdn_scratch(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(self.pwrdn_scratch[index])

    def write_pwrdn_scratch(
        self, size: int, value: int, index: int
    ) -> None:
        if 0 <= index <= 7:
            if self.pwrdn_scratch_lock[0]:
                return

        elif 8 <= index <= 15:
            if self.pwrdn_scratch_lock[1]:
                return

        self.pwrdn_scratch[index] = value

    def read_pwrdn_scratch_lock(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(int(self.pwrdn_scratch_lock[index]))

    def write_pwrdn_scratch_lock(
        self, size: int, value: int, index: int
    ) -> None:
        if value:
            self.pwrdn_scratch_lock[index] = True

    def read_rstsrc(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.rstsrc)

    def write_rstsrc(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "PMU", "RSTSRC")

    def read_clrrst(self, size: int, queue: queue.Queue) -> None:
        unhandled_register_io(prints, "READ", "PMU", "CLRRST")
        queue.put(0)

    def write_clrrst(self, size: int, value: int) -> None:
        if value:
            self.rstsrc = 0

    def read_rst(self, size: int, queue: queue.Queue, index: int) -> None:
        queue.put(0)

    def write_rst(self, size: int, value: int, index: int) -> None:
        # Implement component resetting.
        if self.rst_wr_en[index]:
            # Reset here
            pass

        return

    def read_rst_wr_en(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(int(self.rst_wr_en[index]))

    def write_rst_wr_en(
        self, size: int, value: int, index: int
    ) -> None:
        self.rst_wr_en[index] = bool(value)

    def read_long_life_scratch(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(self.long_life_scratch[index])

    def write_long_life_scratch(
        self, size: int, value: int, index: int
    ) -> None:
        if self.long_life_scratch_wr_en[index]:
            self.long_life_scratch[index] = value

    def read_long_life_scratch_wr_en(
        self, size: int, queue: queue.Queue
    ) -> None:
        val = 0
        for bit in range(4):
            if self.long_life_scratch_wr_en[bit]:
                val |= 1 << bit

        queue.put(val)

    def write_long_life_scratch_wr_en(
        self, size: int, value: int
    ) -> None:
        for bit in range(4):
            if value & (1 << bit):
                self.long_life_scratch_wr_en[bit] = True
            else:
                self.long_life_scratch_wr_en[bit] = False


def init_PowerManagementUnit(
    ctx: EmulatorContext, regs: dict
) -> ComponentObjects:
    c_emu = PowerManagementUnit(ctx)
    c_emu.start_worker()

    reg_fn_map = {
        regs["CHIP_ID"]: [c_emu.read_chip_id, c_emu.write_chip_id],
        regs["SW_PDB"]: [c_emu.read_sw_pdb, c_emu.write_sw_pdb],
        regs["INT_ENABLE"]: [c_emu.read_int_enable, c_emu.write_int_enable],
        regs["EXITPD_MASK"]: [c_emu.read_exitpd_mask, c_emu.write_exitpd_mask],
        regs["LOW_POWER_DIS"]: [
            c_emu.read_low_power_dis,
            c_emu.write_low_power_dis,
        ],
        regs["PERICLKSET0"]: [c_emu.read_periclkset0, c_emu.write_periclkset0],
        regs["PERICLKCLR0"]: [c_emu.read_periclkclr0, c_emu.write_periclkclr0],
        regs["PERICLKSET1"]: [c_emu.read_periclkset1, c_emu.write_periclkset1],
        regs["PERICLKCLR1"]: [c_emu.read_periclkclr1, c_emu.write_periclkclr1],
        regs["CLRRST"]: [c_emu.read_clrrst, c_emu.write_clrrst],
        regs["RSTSRC"]: [c_emu.read_rstsrc, c_emu.write_rstsrc],
        regs["LONG_LIFE_SCRATCH_WR_EN"]: [
            c_emu.read_long_life_scratch_wr_en,
            c_emu.write_long_life_scratch_wr_en,
        ],
    }

    idx_regs_to_regmap(
        reg_fn_map,
        regs["LONG_LIFE_SCRATCH"],
        c_emu.read_long_life_scratch,
        c_emu.write_long_life_scratch,
    )

    idx_regs_to_regmap(
        reg_fn_map,
        regs["PWRDN_SCRATCH"],
        c_emu.read_pwrdn_scratch,
        c_emu.write_pwrdn_scratch,
    )

    idx_regs_to_regmap(
        reg_fn_map,
        regs["PWRDN_SCRATCH_LOCK"],
        c_emu.read_pwrdn_scratch_lock,
        c_emu.write_pwrdn_scratch_lock,
    )

    idx_regs_to_regmap(
        reg_fn_map,
        regs["RST_WR_EN"],
        c_emu.read_rst_wr_en,
        c_emu.write_rst_wr_en,
    )

    idx_regs_to_regmap(reg_fn_map, regs["RST"], c_emu.read_rst, c_emu.write_rst)

    def component_read_handler(
        uc: qemu.Uc, offset: int, size: int, user_data: typing.Any
    ) -> int | None:
        try:
            return c_emu.queue_read_worker_op(size, reg_fn_map[offset][0])
        except KeyError:
            unhandled_register_exit(ctx, prints, "PMU", offset)
            return 0

    def component_write_handler(
        uc: qemu.Uc, offset: int, size: int, value: int, user_data: typing.Any
    ) -> None:
        try:
            c_emu.queue_write_worker_op(size, value, reg_fn_map[offset][1])
        except KeyError:
            unhandled_register_exit(ctx, prints, "PMU", offset)

    return ComponentObjects(
        c_emu, component_read_handler, component_write_handler
    )
