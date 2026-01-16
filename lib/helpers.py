# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import typing

from lib.globalvars import *
from lib.logger import GscemuLogger

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

def unhandled_register_exit(
    logger: GscemuLogger, 
    component: str, 
    address: int
) -> None:
    logger.fatal(f"Unhandled register 0x{address:x} in component {component}!")
    halt_emulation()

def unhandled_register_io(
    logger: GscemuLogger, 
    io_type: str, 
    component: str, 
    subcomponent: str
) -> None:
    logger.warning(f"Unhandled {io_type} to {component}, {subcomponent}!")

def args_lambda_gen(
    reg_fn: typing.Callable, *fixed_args
) -> typing.Callable:
    """Returns a lambda object to handle fixed argument values for a function.
    
    Example:
        regread_lambda_gen(reg_fn, 2, 10) -> lambda x, y: reg_fn(x, y, 10)
    """

    # We need to use eval here. Of course, this will slow down initialization,
    # but it is better than runtime slowdown.

    num_changing_args = reg_fn.__code__.co_argcount - 1 - len(fixed_args)
    
    argenv = {}
    argenv["reg_fn"] = reg_fn

    changing_argstring = str()
    for argnum in range(num_changing_args):
        if argnum > 0:
            changing_argstring = changing_argstring + ", "
        changing_argstring = changing_argstring + f"a{argnum}"

    fixed_argstring = str()
    for argnum, argval in enumerate(fixed_args):
        fixed_argstring = fixed_argstring + f", b{argnum}"
        argenv[f"b{argnum}"] = argval

    return eval(
        f"lambda {changing_argstring}: " + 
        f"reg_fn({changing_argstring}{fixed_argstring})",
        argenv
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
            args_lambda_gen(write_fn, idx)
        ]

def halt_emulation():
    if ucmutex():
        with ucmutex().mutex:
            g_uc().emu_stop()
            prints.debug(
                "Emulation forcefully halted at " +
                f"pc=0x{g_uc().reg_read(qemu.arm_const.UC_ARM_REG_PC):x}"
            )
    else:
        prints.warning("halt_emulation called whilst UcMutex uninitialized!")