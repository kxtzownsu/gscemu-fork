# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

"""File to contain all MMIO component names to their respective r/w handlers

{regname}: [{read_handler_fn}, {write_handler_fn}]
"""

# Manual import of the component handlers. Refactor in the future?
import src.components.m3 as m3
import src.components.uart as uart0
import src.components.fuse as fuse0
import src.components.flash as flash0
import src.components.globalsec as globalsec0
import src.components.keymgr as keymgr0
import src.components.timels as timels0
import src.components.crypto as crypto0

def blank_read_handler(*args, **kwargs) -> int:
    return 0

def blank_write_handler(*args, **kwargs) -> None:
    return

MMIO_HANDLERS = {
    "GLOBALSEC": [globalsec0.component_read_handler, globalsec0.component_write_handler],
    "FUSE0": [fuse0.component_read_handler, fuse0.component_write_handler],
    "TIMELS0": [timels0.component_read_handler, timels0.component_write_handler],
    "KEYMGR0": [keymgr0.component_read_handler, keymgr0.component_write_handler],
    "UART0": [uart0.component_read_handler, uart0.component_write_handler],
    "UART1": [blank_read_handler, blank_write_handler],
    "UART2": [blank_read_handler, blank_write_handler],
    "FLASH0": [flash0.component_read_handler, flash0.component_write_handler],
    "M3": [m3.component_read_handler, m3.component_write_handler],
    "CRYPTO0": [crypto0.component_read_handler, crypto0.component_write_handler],
}