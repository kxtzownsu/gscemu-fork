# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

"""File that contains all emulator hooks.

After some contemplation, I felt that a seperate file was needed to store the
hook functions, since they shouldn't be a part of the class that is exposed
to the user. We could make a seperate class in the future instead?
"""

import typing
import unicorn as qemu

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from .registers import REG_DEFS

from src.components.m3 import pend_svcall_interrupt, exc_return_handler

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

# TODO(appleflyer): hook up with M3 component in the future for interrupts.
def mem_invalid_access(
    uc: qemu.Uc,
    access,
    address: int,
    size: int,
    value: int,
    user_data
) -> bool:
    kind = {
        qemu.UC_MEM_READ_UNMAPPED: "READ", 
        qemu.UC_MEM_WRITE_UNMAPPED: "WRITE", 
        qemu.UC_MEM_FETCH_UNMAPPED: "FETCH",
    }

    prints.fatal(
        f"Invalid memory {kind[access]} " + 
        f"with address=0x{address:08x}, size={size}"
    )
    
    return False

def intr_hook(
    uc: qemu.Uc,
    intno: int, 
    user_data: typing.Any,
):
    match intno:
        case 2: # EXCP_SWI
            pend_svcall_interrupt()
        case 8: # EXCP_EXCEPTION_EXIT
            exc_return_handler()
        case _:
            print(f"unhandled intr {intno}")
            
    return True

def pc_logger(
    uc: qemu.Uc,
    address: int,
    size: int,
    user_data: typing.TextIO,
) -> bool:
    user_data.write(f"{hex(address)}\n")
    user_data.flush()

def blank_tick_hook(
    uc: qemu.Uc,
    address: int,
    size: int,
    user_data: typing.TextIO, 
) -> bool:
    return True