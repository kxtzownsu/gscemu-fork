# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import typing
import unicorn as qemu

from env import *
from lib.globalvars import *
from lib.logger import GscemuLogger
from .regdefs import FUSE_DEFAULTS

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

def component_read_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    user_data: typing.Any,
) -> bool:
    # Check if we have a value for the FUSE that is being asked for. If we
    # don't, just return a blanked FUSE value.
    try:
        # FUSE register in our list of known fuse values, return our known val.
        return FUSE_DEFAULTS[offset]

    except KeyError:
        # FUSE register not in our list of known fuse values, give a blank fuse.
        return 0x55555555
    
def component_write_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    value: int,
    user_data: typing.Any,
) -> None:
    # As of now, FUSE only accepts read operations, not write operations. It is
    # not documented if FUSE supports write operations, but with what we know,
    # FUSE means eFuse, which is basically like the ROM.
    return