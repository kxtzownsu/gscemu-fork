# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

from lib.logger import GscemuLoggerSettings

GSCEMULATOR_LOGGER_SETTINGS = GscemuLoggerSettings(
    global_switch=False,
    debug_prints=True,
    info_prints=True,
    warning_prints=True,
)

GSCEMULATOR_FW_PATHS = {
    "bootrom": "fw/rom/haven.rom",
    "firmware": "fw/haven/cr50_prod_0_5_271.bin"
}
GSCEMULATOR_FW_STRICT_SIZE_CHECKING = False

# Always force SB_COMP_STATUS to True within GLOBALSEC
GSCEMULATOR_FORCE_SB_COMP_STATUS = False

GSCEMULATOR_PC_LOGGING_SETTINGS = {
    "log_pc": False,
    "log_file_path": "./pc.txt",
}