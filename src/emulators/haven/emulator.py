# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

"""Main file that contains the Emulator object and all it's logic.

The emulator emulates the H1B3C chip, which is to say:
- H1 chip
- RevB ver 3
- Chromebook

The H1B3C's CPU runs off the Cortex-M3 armv7m spec.
"""

# Note: Redundancy checks should be applied here as much as possible. This is
# only the initialization phase of the emulator, and therefore runtime does not
# matter as much in this part of the code. We will try to increase debugability
# as much as possible and not consider extra initialization time as wasted time.

import traceback
import unicorn as qemu

from lib.globalvars import *
from .init_utils import *
from . import hooks
from .registers import REG_DEFS, MMIO_REG_DEFS
from lib.logger import GscemuLogger
from lib.threadutils import UcMutex

from src.components.m3 import c_emu as m3_emu

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

class Emulator:
    """Emulator object for the haven chip."""
    
    def __init__(
        self, 
        fw_paths: dict, 
        strict_fw_size_checks: bool
    ) -> None:
        """Initializes the emulator.
        
        Initializes all the components of the emulator like the unicorn engine,
        components, registers, etc.
        """

        prints.info("Initializing emulator...")

        self.init_vtor_val = 0x0
        self.initialized = False

        # For the H1B3C, we're running a ARM Cortex-M3 chip, or at least that's
        # what's documented.
        self.uc = qemu.Uc(
            qemu.UC_ARCH_ARM,
            qemu.UC_MODE_THUMB,
            qemu.arm_const.UC_CPU_ARM_CORTEX_M3
        )
        
        # Assign the global uc variable to our created Uc object. This is
        # accessible through g_uc(). This also creates the UcMutex, accessible 
        # through ucmutex().
        assign_global_uc(self.uc)
        
        # TODO(appleflyer): increase the debugability of the init process.

        if not map_memory(REG_DEFS, MMIO_REG_DEFS):
            prints.fatal("Failed to map memory during init process!")
            return
        
        prepare_info1_space()

        if not load_firmware(
                REG_DEFS, 
                fw_paths, 
                strict_fw_size_checks,
        ):
            prints.fatal("Failed to load firmware during init process.")
            return
        
        # We need to also capture invalid memory accesses. We should integrate
        # this with the M3 in the future. MemManage intr?
        g_uc().hook_add(UNICORN_MEM_INVALID_HOOKS, hooks.mem_invalid_access)
        
        # Call this after the emulator has finished initializing.
        self.initialized = True
        prints.info("Emulator initialization success!")

    def start_emulation(self) -> None:
        """Run the emulator."""

        prints.info("Emulation start signal recieved.")

        if not self.initialized:
            prints.info("Emulator has not been initialized properly. Refusing "
                        + "to start emulation!")
            return
        
        # TODO(appleflyer): when the emulator is more developed, implement
        # custom VTOR offsets.
        
        # We need to load the emulator with the correct pc & sp values before
        # we start the emulator.
        entry_sp = int.from_bytes(
            g_uc().mem_read(self.init_vtor_val + 0x0, 0x4), 
            'little'
        )
        entry_pc = int.from_bytes(
            g_uc().mem_read(self.init_vtor_val + 0x4, 0x4), 
            'little'
        )

        prints.debug(f"VTOR: pc=0x{entry_pc:x}, sp=0x{entry_sp:x}")
        g_uc().reg_write(qemu.arm_const.UC_ARM_REG_SP, entry_sp)
        g_uc().reg_write(qemu.arm_const.UC_ARM_REG_PC, entry_pc)
    
        prints.debug("Starting emulation at " +
                     f"pc=0x{entry_pc:x}")
        
        # Start the CYCCNT timer to count how many cycles have elapsed.
        m3_emu.start_cyccnt_time()

        try:
            g_uc().emu_start(entry_pc, 0xFFFFFFFF)
        except Exception as e:
            current_pc = ucmutex().reg_read(qemu.arm_const.UC_ARM_REG_PC)
            prints.fatal(f"Exception occured at pc=0x{current_pc:x}:")
            traceback.print_exc()