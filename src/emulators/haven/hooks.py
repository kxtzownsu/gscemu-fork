# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

"""File that contains all emulator hooks.

After some contemplation, I felt that a seperate file was needed to store the
hook functions, since they shouldn't be a part of the class that is exposed
to the user. We could make a seperate class in the future instead?
"""

import unicorn as qemu

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from .registers import REG_DEFS

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

    prints.warning(
        f"Invalid memory {kind[access]} " + 
        f"with address=0x{address:08x}, size={size}")
    return False