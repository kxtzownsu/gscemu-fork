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

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from lib.threadutils import FifoLock
from src.emulators.haven.registers import M3_REGS
from lib.helpers import unhandled_register_io, unhandled_register_exit

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

_CYCCNT_SPEED = (1/24000000) * 1000000000

class ArmSC300:
    def __init__(self):
        self.mutex = FifoLock()
        self.cpuid = 0x410fc331 # Known CPUID for the ArmSC300

        self.cyccnt_time_start = 0
        self.itcmcr = 0
        self.demcr = 0
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
}

def component_read_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    user_data: typing.Any,
) -> int:
    try:
        return _REG_FUNC_MAP[offset][0](size)
    except KeyError:
        unhandled_register_exit(prints, "M3", offset)

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
        unhandled_register_exit(prints, "M3", offset)