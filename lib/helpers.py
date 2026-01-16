# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import inspect
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