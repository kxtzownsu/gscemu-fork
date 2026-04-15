# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

"""File to contain all MMIO component names to their respective r/w handlers

{regname}: [{read_handler_fn}, {write_handler_fn}]
"""
from lib.emulator_context import EmulatorContext, ComponentObjects
from .components import regdefs 

# Manual import of the component handlers. Refactor in the future?
from .components import m3
from .components import uart
from .components import fuse
from .components import flash
from .components import globalsec
from .components import keymgr
from .components import timels
from .components import crypto
from .components import usb
from .components import gpio
from .components import trng
from .components import pinmux
from .components import swdp
from .components import pmu
from .components import sps

def blank_read_handler(*args, **kwargs) -> int:
    return 0

def blank_write_handler(*args, **kwargs) -> None:
    return

blank_component = ComponentObjects(
    None, blank_read_handler, blank_write_handler
)

def initialize_components(ctx: EmulatorContext):
    ctx.components["M3"] = m3.init_ArmSC300(ctx, regdefs.M3_REGS)
    ctx.c_fast.m3 = ctx.components["M3"].object

    ctx.components["TIMELS0"] = timels.init_LowSpeedTimer(ctx, regdefs.TIMELS_REGS)
    ctx.c_fast.timels = ctx.components["TIMELS0"].object

    ctx.components["GLOBALSEC"] = globalsec.init_HavenGlobalsec(ctx, regdefs.GLOBALSEC_REGS)
    ctx.components["FLASH0"] = flash.init_FlashController(ctx, regdefs.FLASH_REGS)
    ctx.components["FUSE0"] = fuse.init_eFuses(ctx, regdefs.fuse_registers.FUSE_DEFAULTS)
    ctx.components["SWDP0"] = swdp.init_ARMSoftwareDebugPort(ctx, regdefs.SWDP_REGS)
    ctx.components["PMU"] = pmu.init_PowerManagementUnit(ctx, regdefs.PMU_REGS)

    ctx.components["UART0"] = uart.init_UartController(ctx, regdefs.UART_REGS)
    ctx.c_fast.uart0 = ctx.components["UART0"].object

    ctx.components["UART1"] = blank_component
    ctx.components["UART2"] = blank_component

    ctx.components["KEYMGR0"] = keymgr.init_KeymgrController(ctx, regdefs.KEYMGR_REGS)
    ctx.components["CRYPTO0"] = crypto.init_CryptoAccelerator(ctx, regdefs.CRYPTO_REGS)
    ctx.components["TRNG0"] = trng.init_TRNGEngine(ctx, regdefs.TRNG_REGS)

    ctx.components["GPIO0"] = gpio.init_GpioController(ctx, regdefs.GPIO_REGS, 0)
    ctx.components["GPIO1"] = gpio.init_GpioController(ctx, regdefs.GPIO_REGS, 1)
    ctx.components["PINMUX"] = pinmux.init_Cr50Pinmux(ctx, regdefs.PINMUX_REGS)
    
    ctx.components["USB0"] = usb.init_UsbController(ctx, regdefs.USB_REGS)
    ctx.components["SPS0"] = sps.init_SPISlaveDevice(ctx, regdefs.SPS_REGS)