# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import unicorn as qemu

from env import *
from lib.globalvars import *
from lib.logger import GscemuLogger
from src.emulators.haven.registers import REG_DEFS
from src.emulators.haven.fuse_registers import *

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

_REG_BASE_ADDR = REG_DEFS["FUSE0"]["base_addr"]

def component_handler(uc: qemu.Uc,
                      access,
                      address: int,
                      size: int,
                      value: int,
                      user_data
                      ) -> bool:
    reg_offset = address - _REG_BASE_ADDR

    # As of now, FUSE only accepts read operations, not write operations. It is
    # not documented if FUSE supports write operations, but with what we know,
    # FUSE means eFuse, which is basically like the ROM.
    if not access == qemu.UC_MEM_READ:
        return True
    
    # Check if we have a value for the FUSE that is being asked for. If we
    # don't, just return a blanked FUSE value.
    try:
        # FUSE register in our list of known fuse values, return our known val.
        ucmutex().mem_write(
            address, 
            (DEFAULT_FUSE_VALUES[reg_offset]).to_bytes(4, 'little')
        )

    except KeyError:
        # FUSE register not in our list of known fuse values, give a blank fuse.
        ucmutex().mem_write(
            address, 
            (0x55555555).to_bytes(4, 'little')
        )

    return True
        