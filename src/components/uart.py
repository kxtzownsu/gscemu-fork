# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import unicorn as qemu

from env import *
from lib.logger import GscemuLogger
from src.emulators.haven.registers import REG_DEFS, UART_REGS
from lib.helpers import unhandled_register_exit

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

_REG_BASE_ADDR = REG_DEFS["UART0"]["base_addr"]

def component_handler(instance: int,
                      uc: qemu.Uc,
                      access,
                      address: int,
                      size: int,
                      value: int,
                      user_data
                      ) -> bool:
    """Main component handler for UART"""
    
    # UART 1 and 2 is actually redundant, but we need it for compatibility
    # with guest code that expects these peripherals to exist. It is pointless
    # to support UART 1 and 2, it's not connected to anything.
    if instance in [1, 2]:
        prints.warning("We do not manage UART1-2, it is AP/EC related.")

    # If we do intend to support UART1 and 2, this code needs to be refactored
    # for such a purpose. The code only supports UART0 reads/writes for now.
    reg_offset = address - _REG_BASE_ADDR

    if reg_offset == UART_REGS["WDATA"]:
        if access == qemu.UC_MEM_READ:
            pass

        elif access == qemu.UC_MEM_WRITE:
            pass

    else:
        unhandled_register_exit(prints, "UART", address)

def component0_handler(uc: qemu.Uc,
                      access,
                      address: int,
                      size: int,
                      value: int,
                      user_data
                      ) -> bool:
    """Instance handler for UART0"""

    return component_handler(0, uc, access, address, size, value, user_data)

def component1_handler(uc: qemu.Uc,
                      access,
                      address: int,
                      size: int,
                      value: int,
                      user_data
                      ) -> bool:
    """Instance handler for UART1"""

    return component_handler(1, uc, access, address, size, value, user_data)

def component2_handler(uc: qemu.Uc,
                      access,
                      address: int,
                      size: int,
                      value: int,
                      user_data
                      ) -> bool:
    """Instance handler for UART2"""

    return component_handler(2, uc, access, address, size, value, user_data)