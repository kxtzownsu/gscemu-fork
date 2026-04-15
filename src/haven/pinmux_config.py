# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

from .components.pinmux import Cr50Pinmux
from lib.pindevice import PinStatus
from env import *

def init_strap_config(pinmux: Cr50Pinmux):
    # SPI strap config: DIOA12 = 1M PD, DIOA6 = 1M PD
    pinmux.dioa[6].set_pininfo(PinStatus.PULLDOWN, 1_000_000)
    pinmux.dioa[12].set_pininfo(PinStatus.PULLDOWN, 1_000_000)

    # Poppy specific strap: DIOA9 = 1M PU, DIOA1 = 1M PU
    # (BOARD_PERIPH_CONFIG_SPI | BOARD_USE_PLT_RESET)
    pinmux.dioa[9].set_pininfo(PinStatus.PULLUP, 1_000_000)
    pinmux.dioa[1].set_pininfo(PinStatus.PULLUP, 1_000_000)

def init_custom_board_pinmux_features(pinmux: Cr50Pinmux):
    # DIOM2 is connected to BATT_PRESS_L
    pinmux.diom[2].set_pininfo(PinStatus.PULLUP, 5_000)

    # Using PLT_RESET, so DIOM3 is connected to TPM_RST_L
    pinmux.diom[3].set_pininfo(PinStatus.PULLUP, 5_000)

    if GSCEMULATOR_ASSERT_SPIFLASH_PIN:
        # Pull DIOB4 up for spiflash
        pinmux.diob[4].set_pininfo(PinStatus.PULLUP, 5_000)