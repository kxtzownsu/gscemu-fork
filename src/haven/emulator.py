# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

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

# For unicorn debug builds to analyze the TCG logs.
# import os
# os.environ['UNICORN_LOG_LEVEL'] = "0xFFFFFFFF"
# os.environ['UNICORN_LOG_DETAIL_LEVEL'] = "1"

import traceback
import unicorn as qemu

from lib.emulator_context import EmulatorContext
from .c_fastlookup import ComponentFastLookup
from .init_utils import *
from .pinmux_config import *
from . import hooks
from .components.regdefs import REG_DEFS, MMIO_REG_DEFS
from lib.logger import GscemuLogger
from .mmio_map import initialize_components

from .components.uart import cr50_uart_input

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
        self.pc_logger = None

        # For the H1B3C, we're running a ARM Cortex-M3 chip, or at least that's
        # what's documented.
        self.uc = qemu.Uc(
            qemu.UC_ARCH_ARM,
            qemu.UC_MODE_THUMB | qemu.UC_MODE_MCLASS,
            qemu.arm_const.UC_CPU_ARM_CORTEX_M3
        )

        # Initialize EmulatorContext so that the unicorn engine class can be 
        # passed to other classes and other components.
        self.ctx = EmulatorContext(self.uc)

        # Fast lookup, dictionaries are inefficient over time compared to a 
        # direct pointer.
        self.ctx.c_fast = ComponentFastLookup()
        
        # TODO(appleflyer): increase the debugability of the init process.

        initialize_components(self.ctx)

        if not map_memory(self.ctx, REG_DEFS, MMIO_REG_DEFS):
            prints.fatal("Failed to map memory during init process!")
            return
        
        # On the Cr50, the program flash is filled with FFs. We know this as
        # dumping the entire program flash reveals the unused portions are
        # FFed out. This is also confirmed in the Cr50 FLASH driver code where
        # it states that bits can only be set to 0 from 1, and re-setting
        # a bit to 1 requires that page to be wiped.
        prepare_flash_space(self.ctx)

        # Now, load the program/firmware into the program flash.
        if not load_firmware(
            self.ctx,
            REG_DEFS, 
            fw_paths, 
            strict_fw_size_checks,
        ):
            prints.fatal("Failed to load firmware during init process.")
            return
        
        install_tpm_endorsement_certs(self.ctx)

        init_strap_config(self.ctx)
        init_custom_board_pinmux_features(self.ctx)
        
        self.ctx.uc.hook_add(
            qemu.UC_HOOK_INTR, hooks.intr_hook, user_data=self.ctx
        )
        
        # We need to also capture invalid memory accesses to trigger
        # exceptions.
        self.ctx.uc.hook_add(
            (
                qemu.UC_HOOK_MEM_READ_UNMAPPED |
                qemu.UC_HOOK_MEM_WRITE_UNMAPPED |
                qemu.UC_HOOK_MEM_FETCH_UNMAPPED
            ), 
            hooks.mem_invalid_access, user_data=self.ctx
        )

        # On an external interrupt, we shouldn't just branch to the interrupt
        # directly. We need to wait until we are in a defined emulator state.
        # Using UC_HOOK_BLOCK fixes this, although now external interrupts can 
        # only occur on a UC_HOOK_BLOCK.
        #
        # Interrupting on an external interrupt directly while in an undefined
        # emulator state may cause emu_stop/emu_start on MMIO_MAP callback,
        # which is very dangerous. It is impossible to determine if we have 
        # returned from an MMIO_MAP callback, or if we are still in an MMIO_MAP 
        # callback.
        #
        # Albeit slow, this is the only way to fix the issue at this current
        # point in time.
        self.ctx.uc.hook_add(
            qemu.UC_HOOK_BLOCK, 
            hooks.m3_interrupt_safe_point, user_data=self.ctx
        )

        # We need to manually handle the wfi instruction as our interrupt
        # handler is here.
        self.ctx.uc.hook_add(
            qemu.UC_HOOK_INSN, hooks.handle_wfi_instruction, self.ctx, 
            1, 0, qemu.arm_const.UC_ARM_INS_WFI
        )

        if GSCEMULATOR_PC_LOGGING_SETTINGS["log_pc"]:
            self.pc_logger = open(
                GSCEMULATOR_PC_LOGGING_SETTINGS["log_file_path"], "w"
            )
            self.ctx.uc.hook_add(
                qemu.UC_HOOK_CODE, hooks.pc_logger, self.pc_logger
            )
        
        # Call this after the emulator has finished initializing.
        self.initialized = True
        prints.info("Emulator initialization success!")

    def uart_input(self, input: int) -> None:
        cr50_uart_input(self.ctx.c_fast.uart0, input)

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
            self.ctx.uc.mem_read(self.init_vtor_val + 0x0, 0x4), 
            'little'
        )
        entry_pc = int.from_bytes(
            self.ctx.uc.mem_read(self.init_vtor_val + 0x4, 0x4), 
            'little'
        )

        prints.debug(f"VTOR: pc=0x{entry_pc:x}, sp=0x{entry_sp:x}")
        self.ctx.uc.reg_write(qemu.arm_const.UC_ARM_REG_SP, entry_sp)
        self.ctx.uc.reg_write(qemu.arm_const.UC_ARM_REG_PC, entry_pc)
    
        prints.debug("Starting emulation at " +
                     f"pc=0x{entry_pc:x}")
        
        # Start the CYCCNT timer to count how many cycles have elapsed.
        self.ctx.components["M3"].object.start_cyccnt_time()

        self.ctx.ucthread.emu_start()