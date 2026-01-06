from lib.logger import GscemuLoggerSettings

GSCEMULATOR_LOGGER_SETTINGS = GscemuLoggerSettings(
    global_switch=True,
    debug_prints=True,
    info_prints=True,
    warning_prints=True,
)

GSCEMULATOR_FW_PATHS = {
    "bootrom": "fw/roms/haven.rom",
    "firmware": "fw/cr50/0_5_271.bin"
}
GSCEMULATOR_FW_STRICT_SIZE_CHECKING = True