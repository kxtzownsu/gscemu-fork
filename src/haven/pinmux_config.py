# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

from lib.pindevice import PinStatus
from .components.pinmux import c_emu as pinmux

def init_strap_config():
    # Poppy strap configuration, DIOA9 = 1M PU, DIOA1 = 1M PU
    # (BOARD_PERIPH_CONFIG_SPI | BOARD_USE_PLT_RESET)
    pinmux.dioa[9].set_pininfo(PinStatus.PULLUP, 1_000_000)
    pinmux.dioa[1].set_pininfo(PinStatus.PULLUP, 1_000_000)

def init_custom_board_pinmux_features():
    # DIOM2 is connected to BATT_PRESS_L
    pinmux.diom[2].set_pininfo(PinStatus.PULLUP, 10_000)

    # Using PLT_RESET, so DIOM3 is connected to TPM_RST_L
    pinmux.diom[3].set_pininfo(PinStatus.PULLUP, 10_000)