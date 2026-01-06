# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import unicorn as qemu

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from lib.threadutils import FifoLock
from src.emulators.haven.registers import REG_DEFS, GLOBALSEC_REGS
from lib.helpers import unhandled_register_io, unhandled_register_exit

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

_REG_BASE_ADDR = REG_DEFS["GLOBALSEC"]["base_addr"]

class HavenGlobalsec:
    def __init__(self):
        self.mutex = FifoLock()
        self.alert_control = 0

    def read_alert_control(self, addr: int) -> None:
        with self.mutex:
            ucmutex().mem_write(
                addr, 
                (self.alert_control).to_bytes(4, 'little')
            )

    def write_alert_control(self, val: int) -> None:
        with self.mutex:
            self.alert_control = val

c_emu = HavenGlobalsec()

_REG_FUNC_MAP = {
    GLOBALSEC_REGS["ALERT_CONTROL"]: [c_emu.read_alert_control, 
                                      c_emu.write_alert_control],

}

def component_handler(uc: qemu.Uc,
                      access,
                      address: int,
                      size: int,
                      value: int,
                      user_data
                      ) -> bool:
    """Main component handler for GLOBALSEC"""

    reg_offset = address - _REG_BASE_ADDR

    try:
        if access == qemu.UC_MEM_READ:
            _REG_FUNC_MAP[reg_offset][0](address)
        elif access == qemu.UC_MEM_WRITE:
            _REG_FUNC_MAP[reg_offset][1](value)

    except KeyError:
        unhandled_register_exit(prints, "GLOBALSEC", address)