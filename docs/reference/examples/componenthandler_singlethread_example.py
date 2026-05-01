# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer
"""Example component handler"""

import typing
import unicorn as qemu

from lib.emulator_context import EmulatorContext, ComponentObjects
from env import *
from lib.logger import GscemuLogger
from lib.threadutils import FifoLock
from lib.helpers import unhandled_register_exit

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


class ComponentXX:
    def __init__(self):
        self.opmutex = FifoLock()
        self.xy = 0

    def read_xy(self, size: int):
        with self.opmutex:
            return self.xy

    def write_xy(self, size: int, value: int):
        with self.opmutex:
            self.xy = value


def init_ComponentXX(ctx: EmulatorContext, regs: dict):
    c_emu = ComponentXX()

    reg_fn_map = {regs["XY_PART"]: [c_emu.read_xy, c_emu.write_xy]}

    def component_read_handler(
        uc: qemu.Uc,
        offset: int,
        size: int,
        user_data: typing.Any,
    ) -> int:
        try:
            return reg_fn_map[offset][0](size)
        except KeyError:
            unhandled_register_exit(ctx, prints, "XX", offset)

    def component_write_handler(
        uc: qemu.Uc,
        offset: int,
        size: int,
        value: int,
        user_data: typing.Any,
    ) -> None:
        try:
            reg_fn_map[offset][1](size, value)
        except KeyError:
            unhandled_register_exit(ctx, prints, "XX", offset)

    return ComponentObjects(
        c_emu, component_read_handler, component_write_handler
    )
