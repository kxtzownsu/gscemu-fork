# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import functools

from lib.globalvars import *
from lib.logger import GscemuLogger

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

def unhandled_register_exit(
    logger: GscemuLogger, 
    component: str, 
    address: int
) -> None:
    logger.fatal(f"Unhandled register 0x{address:x} in component {component}!")
    halt_emulation()

def unhandled_register_io(
    logger: GscemuLogger, 
    io_type: str, 
    component: str, 
    subcomponent: str
) -> None:
    logger.warning(f"Unhandled {io_type} to {component}, {subcomponent}!")

def idx_regs_to_regmap(
    regmap: list,
    reglist: list,
    read_fn,
    write_fn,
) -> None:
    for idx, offset in enumerate(reglist):
        regmap[offset] = [
            functools.partial(read_fn, index=idx),
            functools.partial(write_fn, index=idx)
        ]

def halt_emulation():
    if ucmutex():
        with ucmutex().mutex:
            g_uc().emu_stop()
            prints.debug(
                "Emulation forcefully halted at " +
                f"pc=0x{g_uc().reg_read(qemu.arm_const.UC_ARM_REG_PC):x}"
            )
    else:
        prints.warning("halt_emulation called whilst UcMutex uninitialized!")