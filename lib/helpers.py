# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

import inspect
import typing

import unicorn as qemu

from env import *
from lib.emulator_context import EmulatorContext
from lib.logger import GscemuLogger
from lib.threadutils import UcMutex
from lib.ucthread import UcThread

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


def unhandled_register_exit(
    ctx: EmulatorContext, logger: GscemuLogger, component: str, address: int
) -> None:
    logger.fatal(
        f"Unhandled register 0x{address:x} in component {component} at "
        + f"pc=0x{ctx.uc.reg_read(qemu.arm_const.UC_ARM_REG_PC):x}"
    )
    halt_emulation(ctx.uc, ctx.ucthread)


def unhandled_register_io(
    logger: GscemuLogger, io_type: str, component: str, subcomponent: str
) -> None:
    logger.warning(f"Unhandled {io_type} to {component}, {subcomponent}!")


def args_lambda_gen(reg_fn: typing.Callable, *fixed_args) -> typing.Callable:
    """Returns a lambda object to handle fixed argument values for a function.

    We can infer the number of changing arguments from the number of fixed
    arguments passed to us and the number of arguments that reg_fn expects.
    With this, we assume all fixed arguments are at the front, and changing
    arguments at the back in order.

    This is a powerful macro to remove expanding (*args, **kwargs) every
    function call, although very costly at the start which takes up a lot of
    setup time.

    Example:
        reg_fn(x, y, z)
        args_lambda_gen(reg_fn, 10) -> lambda x, y: reg_fn(x, y, 10)
    """
    # If we are in a class, we need to -1, because the "self" argument is also
    # counted.
    is_class = int(inspect.ismethod(reg_fn))

    num_changing_args = reg_fn.__code__.co_argcount - is_class - len(fixed_args)

    argenv = {}
    argenv["reg_fn"] = reg_fn

    # Generate the changing args argstring (a0, a1, a2)
    changing_argstring = str()
    for argnum in range(num_changing_args):
        if argnum > 0:
            changing_argstring = changing_argstring + ", "
        changing_argstring = changing_argstring + f"a{argnum}"

    # Generate the fixed args argstring (b0, b1, b2)
    fixed_argstring = str()
    for argnum, argval in enumerate(fixed_args):
        if num_changing_args > 0 or argnum > 0:
            fixed_argstring = fixed_argstring + ", "
        fixed_argstring = fixed_argstring + f"b{argnum}"
        argenv[f"b{argnum}"] = argval

    return eval(
        f"lambda {changing_argstring}: "
        + f"reg_fn({changing_argstring}{fixed_argstring})",
        argenv,
    )


def idx_regs_to_regmap(
    regmap: list,
    reglist: list,
    read_fn,
    write_fn,
) -> None:
    for idx, offset in enumerate(reglist):
        regmap[offset] = [
            args_lambda_gen(read_fn, idx),
            args_lambda_gen(write_fn, idx),
        ]


def armv7m_find_instruction_size(ucmutex: UcMutex, address: int):
    """Find the instruction length of an instruction from it's address.

    Based on the armv7m Cortex-M3 spec, we are using Thumb-2. Therefore,
    we can determine a 2 or 4 byte instruction by looking at the first 2 bytes
    of an instruction. If bytes [15:11] are more than 0x1d, it's a 4 byte
    instruction.
    """
    if ((ucmutex.int16_mem_read(address) >> 11) & 0x1F) >= 0x1D:
        return 4
    else:
        return 2


def write_u32_to_sp(ucmutex: UcMutex, val: int):
    new_sp = ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_SP) - 4
    ucmutex.reg_write(qemu.arm_const.UC_ARM_REG_SP, new_sp)

    ucmutex.mem_write(new_sp, val.to_bytes(4, "little"))


def read_u32_from_sp(ucmutex: UcMutex, sp_type: int):
    sp = ucmutex.reg_read(sp_type)
    val = ucmutex.int32_mem_read(sp)
    ucmutex.reg_write(sp_type, sp + 4)
    return val


def pattern_list_gen(starting_offset, indexes, step=4):
    temp = []
    for index in range(indexes):
        temp.append(starting_offset + (index * step))

    return temp


def halt_emulation(
    uc: qemu.Uc,
    ucthread: UcThread,
) -> None:
    # PC sync is not guaranteed here, so the caller needs to manage this
    # properly if we use this.
    prints.debug(
        "Emulation forcefully halted at "
        + f"pc=0x{uc.reg_read(qemu.arm_const.UC_ARM_REG_PC):x}"
    )
    ucthread.emu_halt()


def extract_max_number(v, current_max=None):
    """
    Extract max numerical value from a int/float/list/dict object.
    This is useful for creating the most memory efficient lists for list based
    register mapping.
    """
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if current_max is None or v > current_max:
            current_max = v

    elif isinstance(v, list):
        for item in v:
            current_max = extract_max_number(item, current_max)

    elif isinstance(v, dict):
        for item in v.values():
            current_max = extract_max_number(item, current_max)

    return current_max
