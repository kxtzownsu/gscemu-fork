# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

"""Contains all the emulator's initialization utilities."""

# Note: Redundancy checks should be applied here as much as possible. This is
# only the initialization phase of the emulator, and therefore runtime does not
# matter as much in this part of the code. We will try to increase debugability
# as much as possible and not consider extra initialization time as wasted time.

import unicorn as qemu

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

def map_memory(mem_map_list: list) -> bool:
    """Helper function to map memory in the emulator.
    
    This is required or we will encounter issues within the emulator where the
    memory is not mapped.
    It is good practice to manually map regions in the memory, not to just map
    everything at once(0x0 to 0xFFFFFFFF).
    """

    try:
        for i in mem_map_list.items():
            prints.debug(f"Mapping {i[0]} with " +
                        f"pc=0x{i[1]["base_addr"]:x}" +
                        f",size=0x{i[1]["size"]:x}")
            g_uc().mem_map(
                i[1]["base_addr"], 
                i[1]["size"]
            )
    except Exception as e:
        # We failed to map the memory, possibly because the base_addr or size
        # was invalid. This is a dev issue and even so, we should handle it
        # properly, to accomodate for forks of this repository.
        return False
    
    return True

def load_firmware(
        mem_map_list: list, 
        fw_paths: dict,
        strict_file_size_checks: bool | None = True,
        ) -> bool:
    """Load firmware into the FLASH_BROM + FLASH_PROG region.
    
    Args:
        mem_map_list:
            List containing all mapped register definitions. This is so we know
            where FLASH_BROM and FLASH_PROG is located.
        fw_paths: 
            Dictionary that contains the path to the firwmare to load.
            BootROM and firmware paths are compulsory!

            {
                "bootrom": "{path}",
                "firmware": "{path}",
                "saved_state": "{path}",
            }
        strict_file_size_checks:
            Boolean to enable or disable strict file size checking. This
            defaults to True if we do.
    """
    # TODO(appleflyer): add saved_state support in the future.

    # Check that BootROM and firmware paths were specified!
    try:
        if not fw_paths["bootrom"]:
            return False
        if not fw_paths["firmware"]:
            return False
    except:
        prints.debug("One or more paths were not specified in fw_paths dict!")
        return False
    
    # Load BootROM into a temp var for size calculation.
    with open(fw_paths["bootrom"], 'rb') as f:
        rom_data = f.read()

    # Check that the BootROM file given has the correct size to load into 
    # memory. If rom_data is too short and we aren't strict, add 0s until it
    # reaches the desired length. Too long a data string will be managed.
    if strict_file_size_checks:
        # Subtract 0x20 from the BootROM size!!
        if not (
                len(rom_data) == 
                (mem_map_list["FLASH_BROM"]["size"] - 0x20)
            ):
            prints.debug("BootROM did not meet size requirements!")
            return False


    # Load RO+RW into a temp var for size calculation.
    with open(fw_paths["firmware"], 'rb') as f:
        fw_data = f.read()

    # Check that the firmware file given has the correct size to load into 
    # memory. If fw_data is too short and we aren't strict, add 0s until it
    # reaches the desired length. Too long a data string will be managed.
    if strict_file_size_checks:
        if not (
                len(fw_data) == 
                (mem_map_list["FLASH_PROG"]["size"])
        ):
            return False

    # Load BootROM into FLASH_BROM
    g_uc().mem_write(mem_map_list["FLASH_BROM"]["base_addr"], 
                     rom_data[:(mem_map_list["FLASH_BROM"]["size"] - 0x20)])

    # Load firmware into FLASH_PROG
    g_uc().mem_write(mem_map_list["FLASH_PROG"]["base_addr"], 
                     fw_data[:mem_map_list["FLASH_PROG"]["size"]])
    
    return True