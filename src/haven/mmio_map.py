# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

"""File to contain all MMIO component names to their respective r/w handlers

{regname}: [{read_handler_fn}, {write_handler_fn}]
"""

# Manual import of the component handlers. Refactor in the future?
from .components import m3 as m3
from .components import uart as uart0
from .components import fuse as fuse0
from .components import flash as flash0
from .components import globalsec as globalsec
from .components import keymgr as keymgr0
from .components import timels as timels0
from .components import crypto as crypto0
from .components import usb as usb0
from .components import gpio
from .components import trng
from .components import pinmux
from .components import swdp as swdp0

def blank_read_handler(*args, **kwargs) -> int:
    return 0

def blank_write_handler(*args, **kwargs) -> None:
    return

MMIO_HANDLERS = {
    "M3": [m3.component_read_handler, m3.component_write_handler],
    "GLOBALSEC": [globalsec.component_read_handler, globalsec.component_write_handler],
    "FLASH0": [flash0.component_read_handler, flash0.component_write_handler],
    "TIMELS0": [timels0.component_read_handler, timels0.component_write_handler],
    "FUSE0": [fuse0.component_read_handler, fuse0.component_write_handler],
    "SWDP0": [swdp0.component_read_handler, swdp0.component_write_handler],

    "UART0": [uart0.component_read_handler, uart0.component_write_handler],
    "UART1": [blank_read_handler, blank_write_handler],
    "UART2": [blank_read_handler, blank_write_handler],

    "KEYMGR0": [keymgr0.component_read_handler, keymgr0.component_write_handler],
    "CRYPTO0": [crypto0.component_read_handler, crypto0.component_write_handler],
    "TRNG0": [trng.component_read_handler, trng.component_write_handler],

    "GPIO0": [gpio.component_read_handler_0, gpio.component_write_handler_0],
    "GPIO1": [gpio.component_read_handler_1, gpio.component_write_handler_1],
    "PINMUX": [pinmux.component_read_handler, pinmux.component_write_handler],

    "USB0": [blank_read_handler, blank_write_handler],
    "SPS0": [blank_read_handler, blank_write_handler],
}