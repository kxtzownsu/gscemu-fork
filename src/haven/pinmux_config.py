# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

from lib.emulator_context import EmulatorContext
from env import *
from lib.pindevice import PinStatus

def init_strap_config(ctx: EmulatorContext):
    # SPI strap config: DIOA12 = 1M PD, DIOA6 = 1M PD
    ctx.components["PINMUX"].object.dioa[6].set_pininfo(PinStatus.PULLDOWN, 1_000_000)
    ctx.components["PINMUX"].object.dioa[12].set_pininfo(PinStatus.PULLDOWN, 1_000_000)

    # Poppy specific strap: DIOA9 = 1M PU, DIOA1 = 1M PU
    # (BOARD_PERIPH_CONFIG_SPI | BOARD_USE_PLT_RESET)
    ctx.components["PINMUX"].object.dioa[9].set_pininfo(PinStatus.PULLUP, 1_000_000)
    ctx.components["PINMUX"].object.dioa[1].set_pininfo(PinStatus.PULLUP, 1_000_000)

def init_custom_board_pinmux_features(ctx: EmulatorContext):
    # DIOM2 is connected to BATT_PRESS_L
    ctx.components["PINMUX"].object.diom[2].set_pininfo(PinStatus.PULLUP, 5_000)

    # Using PLT_RESET, so DIOM3 is connected to TPM_RST_L
    ctx.components["PINMUX"].object.diom[3].set_pininfo(PinStatus.PULLUP, 5_000)

    if GSCEMULATOR_ASSERT_SPIFLASH_PIN:
        # Pull DIOB4 up for spiflash
        ctx.components["PINMUX"].object.diob[4].set_pininfo(PinStatus.PULLUP, 5_000)