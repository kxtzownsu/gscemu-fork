# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

from lib.logger import GscemuLoggerSettings

GSCEMULATOR_LOGGER_SETTINGS = GscemuLoggerSettings(
    global_switch=False,
    debug_prints=False,
    info_prints=False,
    warning_prints=True,
)

GSCEMULATOR_FW_PATHS = {
    "bootrom": "fw/rom/haven.rom",
    "firmware": "fw/haven/cr50_prod_0_5_271.bin"
}
GSCEMULATOR_FW_STRICT_SIZE_CHECKING = False

GSCEMULATOR_PC_LOGGING_SETTINGS = {
    "log_pc": False,
    "log_file_path": "./pc.txt",
}

# -- gscemu debug flags --
# These flags change how the emulator works internally during runtime, and
# may cause unintended effects when any are set. For a prod run, these flags 
# should be disabled!

# Always force SB_COMP_STATUS to True within GLOBALSEC. This allows garbage
# values to be passed into SB_BL_SIG and execution will still be unlocked.
# Decreases BootROM/RO bootup time by ~20-30%
GSCEMULATOR_FORCE_SB_COMP_STATUS = True

# Disable the CRYPTO engine and just claim the CRYPTO engine has finished
# op. This speeds up the emulator as the CRYPTO engine has large speed overhead, 
# but the CRYPTO engine will be unusable.
GSCEMULATOR_DISABLE_CRYPTO_ENGINE = False