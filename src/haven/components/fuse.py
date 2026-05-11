# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

import typing

import unicorn as qemu

from env import *
from lib.emulator_context import ComponentObjects, EmulatorContext
from lib.logger import GscemuLogger

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


def init_eFuses(ctx: EmulatorContext, fuse_const: dict) -> ComponentObjects:
    def component_read_handler(
        uc_unused: qemu.Uc, offset: int, size: int, user_data: typing.Any
    ) -> int:
        # Check if we have a value for the FUSE that is being asked for. If we
        # don't, just return a blanked FUSE value.
        try:
            # FUSE register in our list of known fuse values,
            # return our known val.
            return fuse_const[offset]

        except KeyError:
            # FUSE register not in our list of known fuse values,
            # give a blank fuse.
            return 0x55555555

    def component_write_handler(
        uc_unused: qemu.Uc,
        offset: int,
        size: int,
        value: int,
        user_data: typing.Any,
    ) -> None:
        # As of now, FUSE only accepts read operations, not write operations.
        # It is not documented if FUSE supports write operations,
        # but with what we know, FUSE means eFuse, which is basically
        # like the ROM.
        return

    return ComponentObjects(
        None, component_read_handler, component_write_handler
    )
