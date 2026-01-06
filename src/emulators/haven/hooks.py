# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

"""File that contains all emulator hooks.

After some contemplation, I felt that a seperate file was needed to store the
hook functions, since they shouldn't be a part of the class that is exposed
to the user. We could make a seperate class in the future instead?
"""

import unicorn as qemu

from env import *
from lib.logger import GscemuLogger
from .registers import REG_DEFS

# Manual import of the component handlers. Refactor in the future?
from src.components.globalsec import component_handler as globalsec_handler
from src.components.fuse import component_handler as fuse_handler
from src.components.m3 import component_handler as m3_handler

# Components with multiple instances should be handled this way. We do not want
# to neglect speed just because a component has multiple instances. For example,
# UART is a component that requires high speed to print to the console. Just
# because code is repetitive does not mean it is inefficient.
from src.components.uart import component0_handler as uart0_handler
from src.components.uart import component1_handler as uart1_handler
from src.components.uart import component2_handler as uart2_handler

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

MEM_IO_HANDLERS = {
    "UART0": uart0_handler,
    "UART1": uart1_handler,
    "UART2": uart2_handler,
    "GLOBALSEC": globalsec_handler,
    "FUSE0": fuse_handler,
    "M3": m3_handler,
}

# TODO(appleflyer): hook up with M3 component in the future for interrupts.
def mem_invalid_access(uc: qemu.Uc,
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

    prints.warning(
        f"Invalid memory {kind[access]} " + 
        f"with address=0x{address:08x}, size={size}")
    return False

# We need a better way to handle this. This loops through one dictionary, and
# accesses another large dictionary which is inefficient.
# Hopefully we could do some init optimizations to make this faster.
def mem_io_operation(uc: qemu.Uc,
                      access,
                      address: int,
                      size: int,
                      value: int,
                      user_data
                    ) -> bool:
    for handler_name, handler_fn in MEM_IO_HANDLERS.items():
        if (
            REG_DEFS[handler_name]["base_addr"] <= address < \
            REG_DEFS[handler_name]["base_addr"] + REG_DEFS[handler_name]["size"]
        ):
            return handler_fn(uc, access, address, size, value, user_data)
