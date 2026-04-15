# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

"""File that contains all emulator hooks.

After some contemplation, I felt that a seperate file was needed to store the
hook functions, since they shouldn't be a part of the class that is exposed
to the user. We could make a seperate class in the future instead?
"""

import typing
import unicorn as qemu

from lib.emulator_context import EmulatorContext, ComponentObjects
from env import *
from lib.logger import GscemuLogger

from .components.m3 import (
    pend_svcall_interrupt,
    exc_return_handler,
    handle_externally_pended_interrupts,
    wait_for_interrupt,
    unsafe_pend_sysintr
)

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

# TODO(appleflyer): hook up with M3 component in the future for interrupts.
def mem_invalid_access(
    uc: qemu.Uc,
    access,
    address: int,
    size: int,
    value: int,
    user_data: EmulatorContext
) -> bool:
    kind = {
        qemu.UC_MEM_READ_UNMAPPED: "READ", 
        qemu.UC_MEM_WRITE_UNMAPPED: "WRITE", 
        qemu.UC_MEM_FETCH_UNMAPPED: "FETCH",
    }

    prints.warning(
        f"Bad memory access {kind[access]} at 0x{address:x} on " +
        f"pc=0x{uc.reg_read(qemu.arm_const.UC_ARM_REG_PC):x}." +
        "Emulator will crash soon..."
    )
    if access == qemu.UC_MEM_WRITE_UNMAPPED:
        prints.warning(f"value written = 0x{value:x}")
        
    unsafe_pend_sysintr(5) # BusFault

    # When we return from a UC_MEM_x_UNMAPPED hook, we need to map the memory.
    # Unicorn will try to re-access the memory and crash the emulator.
    # There is no way around this issue as of now, and there's also no
    # UC_ERR_MAP hook to capture this issue.
    page_addr = address & ~0xFFF
    try:
        uc.mem_map(page_addr, 0x1000)
    except qemu.UcError:
        # Mapping already overlaps something else! But honestly this
        # shouldn't even happen.
        pass

    return True

def intr_hook(
    uc: qemu.Uc,
    intno: int, 
    user_data: EmulatorContext,
):
    ctx = user_data

    match intno:
        case 2: # EXCP_SWI
            pend_svcall_interrupt(ctx.c_fast.m3)
        case 8: # EXCP_EXCEPTION_EXIT
            exc_return_handler(ctx.c_fast.m3)
        case _:
            prints.fatal(
                f"unhandled intr={intno}, " +
                f"pc=0x{ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_PC):x}")

    return True

def handle_wfi_instruction(
    uc: qemu.Uc,
    user_data: EmulatorContext,
):
    ctx = user_data

    # Wait until an interrupt is externally pended from an external source.
    wait_for_interrupt(ctx.c_fast.m3)
    
    # Increment past the wfi instruction
    ctx.ucmutex.reg_write(
        qemu.arm_const.UC_ARM_REG_PC, 
        (ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_PC) + 2) | 1
    )
    return True

def m3_interrupt_safe_point(
    uc: qemu.Uc,
    address: int,
    size: int,
    user_data: EmulatorContext,
) -> bool:
    ctx = user_data
    handle_externally_pended_interrupts(ctx.c_fast.m3)
    return True

def pc_logger(
    uc: qemu.Uc,
    address: int,
    size: int,
    user_data: typing.TextIO,
) -> bool:
    user_data.write(f"{hex(address)}\n")
    user_data.flush()

def blank_tick_hook(
    uc: qemu.Uc,
    address: int,
    size: int,
    user_data: typing.TextIO, 
) -> bool:
    return True