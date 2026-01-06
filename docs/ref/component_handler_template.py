# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer
"""Example component handler"""

import unicorn as qemu
import queue

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from lib.threadutils import FifoLock
from src.emulators.haven.registers import REG_DEFS, XX_REGS
from lib.helpers import unhandled_register_exit

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

_REG_BASE_ADDR = REG_DEFS["XX"]["base_addr"]

class ComponentXX:
    def __init__(self):
        pass

c_emu = ComponentXX()

_REG_FUNC_MAP = {
    XX_REGS["XY_PART"]: [c_emu.read_xy, c_emu.write_xy]
}

def component_handler(uc: qemu.Uc,
                      access,
                      address: int,
                      size: int,
                      value: int,
                      user_data
                      ) -> bool:
    """Main component handler for XX"""

    reg_offset = address - _REG_BASE_ADDR

    try:
        if access == qemu.UC_MEM_READ:
            _REG_FUNC_MAP[reg_offset][0](address)
        elif access == qemu.UC_MEM_WRITE:
            _REG_FUNC_MAP[reg_offset][1](value)

    except KeyError:
        unhandled_register_exit(prints, "XX", address)