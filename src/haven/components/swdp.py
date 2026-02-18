# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer
"""SWDP component handler. This is possibly part of the ARM CPU.

The usage of SWDP is really quite undocumented, so not much we can infer.
Based on the Cortex-M3 integration manual, it talks about a "Trickbox" and
"SW-DP" as a debug port. This is also observed in SWDP hw_regdefs.h as 
GC_SWDP_TRICKBOX_HALT_OFFSET and GC_SWDP_TEST_PORT_DISABLE_OFFSET.

It is only possible to assume that they are the same thing, and that SWDP is
indeed a debug peripheral of the Cortex-M3.
"""

import typing
import unicorn as qemu
import queue

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from lib.threadutils import FifoLock
from lib.helpers import unhandled_register_exit
from .regdefs import SWDP_REGS

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

class ARMSoftwareDebugPort:
    def __init__(self):
        self.opmutex = FifoLock()

        # These registers were only used on the FPGA board, on real silicon 
        # they are empty registers and unused.
        self.build_date = 0x0
        self.build_time = 0x0
        self.p4_last_sync = 0x0

    def read_build_date(self, size: int):
        with self.opmutex:
            return self.build_date
    
    def write_build_date(self, size: int, value: int):
        return
    
    def read_build_time(self, size: int):
        with self.opmutex:
            return self.build_time
    
    def write_build_time(self, size: int, value: int):
        return

    def read_p4_last_sync(self, size: int):
        with self.opmutex:
            return self.p4_last_sync
    
    def write_p4_last_sync(self, size: int, value: int):
        return

c_emu = ARMSoftwareDebugPort()

_REG_FUNC_MAP = {
    SWDP_REGS["BUILD_DATE"]: [c_emu.read_build_date, c_emu.write_build_date],
    SWDP_REGS["BUILD_TIME"]: [c_emu.read_build_time, c_emu.write_build_time],
    SWDP_REGS["P4_LAST_SYNC"]: [
        c_emu.read_p4_last_sync, c_emu.write_p4_last_sync
    ],
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
        unhandled_register_exit(g_uc(), ucthread(), prints, "SWDP0", offset)

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
        unhandled_register_exit(g_uc(), ucthread(), prints, "SWDP0", offset)