# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

from lib.globalvars import *
from lib.logger import GscemuLogger

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

def BIT(bit) -> int:
    return 1 << bit

def unhandled_register_exit(logger: GscemuLogger, 
                            component: str, 
                            address: int
                            ) -> None:
    logger.fatal(f"Unhandled register 0x{address:x} in component {component}!")
    halt_emulation()

def unhandled_register_io(logger: GscemuLogger, 
                          io_type: str, 
                          component: str, 
                          subcomponent: str
                          ) -> None:
    logger.warning(f"Unhandled {io_type} to {component}, {subcomponent}!")

def halt_emulation():
    if ucmutex():
        with ucmutex().mutex:
            g_uc().emu_stop()
            prints.debug("Emulation forcefully halted!")
    else:
        prints.warning("halt_emulation called whilst UcMutex uninitialized!")