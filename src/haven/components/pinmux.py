# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer
"""Cr50 PINMUX component

This is a very complicated component, as it requires a lot of integration
with other components, such as UART, SPS, GPIO etc.
"""

import typing
import unicorn as qemu
import queue
import threading
import enum
import fractions

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
#from .regdefs import PINMUX_REGS
from lib.helpers import unhandled_register_exit
from lib.threadutils import FifoLock

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

def _normalize_resistance(resistance_ohms: float) -> float:
    # pd/pu without resistance? Just normalize it to 50k for now.
    if resistance_ohms <= 0:
        prints.warning("_normalize_resistance 50k triggered, invalid val!")
        return 50000.0
    
    return resistance_ohms

def _parallel_ohms(res_list: list[float]) -> float:
    # Follow the 1/R law to calculate resistance in parallel.
    inv = 0.0
    for r in res_list:
        inv += 1.0 / r
    
    if inv:
        # Round to 2dp, we don't need to be that accurate anyways.
        return round(1.0 / inv, 2)
    else:
        return 0.0

class PinStatus(enum.Enum):
    PULLDOWN = enum.auto()
    FLOATING = enum.auto()
    PULLUP = enum.auto()

class PinInfo:
    def __init__(self):
        self.pinstate: PinStatus = PinStatus.FLOATING
        self.resistance_ohms: float = 0.0

EMPTY_PININFO = PinInfo()

class PinDevice:
    """
    This class is used to make pinmux devices, such as for GPIO pins,
    PINMUX pads, SPS connections, etc.
    """
    def __init__(
            self, 
            interrupt_fn: typing.Callable[
                [PinStatus, PinStatus, typing.Any]
            , None] = None, 
            interrupt_fn_userdata: typing.Any | None = None
        ):
        self.lock = FifoLock()

        # The devices that are driving this pin. On the software side, a pin
        # can only have 1 driver. But, PINMUX has an exception where
        # 
        self.driving_me = {
            "INTERNAL": None,
        }

        # The devices that we have been assigned to drive
        self.driving_components = set()

        # The PinInfo that this device exerts onto components that it drives and
        # on itself.
        self.device_pininfo: PinInfo = PinInfo()

        # Factor in the device_pininfo PinInfo from the component driving us 
        # too.
        self.balanced_pininfo: PinInfo = PinInfo()

        # Convenience variable, allows us to disable output on a single pin
        # to mask it to FLOATING, 0.0, without losing state when we re-enable
        # the pin.
        self.mask_device_pininfo = False

        # Optionally, a device might want a signal on FALLING_EDGE/RISING_EDGE.
        # This is needed for GPIO anyways.
        self.interrupt_signal = interrupt_fn
        self.user_data = interrupt_fn_userdata

    def _update_balanced_pininfo(
            self, new_pinstate: PinStatus, resistance: float | int
        ):
        # THIS SHOULD NOT BE CALLED WITHOUT A LOCK!!
        current_pinstate = self.balanced_pininfo.pinstate
        if current_pinstate != new_pinstate:
            self.balanced_pininfo.pinstate = new_pinstate

            if self.interrupt_signal:
                # Caller should handle this interrupt signal properly,
                # else they might get stale data.
                self.interrupt_signal(
                    current_pinstate, new_pinstate, self.user_data
                )

        self.balanced_pininfo.resistance_ohms = float(resistance)

    def drive_by_component(self, driver: PinDevice):
        # Someone will drive us.
        with self.lock:
            if self.driving_me["INTERNAL"]:
                with self.driving_me["INTERNAL"].lock:
                    # We should not KeyError, it is impossible.
                    # If it happens then we should catch it!
                    self.driving_me["INTERNAL"].driving_components.remove(self)

            self.driving_me["INTERNAL"] = driver
            with self.driving_me["INTERNAL"].lock:
                driver.driving_components.add(self)

        self.pininfo_sync()

    def disconnect_driver(self):
        with self.lock:
            if self.driving_me["INTERNAL"]:
                with self.driving_me["INTERNAL"].lock:
                    # We should not KeyError, it is impossible.
                    # If it happens then we should catch it!
                    self.driving_me["INTERNAL"].driving_components.remove(self)

                self.driving_me["INTERNAL"] = None

        self.pininfo_sync()

    def add_external_drive_by_component(self, tag: str, driver: PinDevice):
        with self.lock:
            if self.driving_me[tag]:
                with self.driving_me[tag].lock:
                    # We should not KeyError, it is impossible.
                    # If it happens then we should catch it!
                    self.driving_me[tag].driving_components.remove(self)

            self.driving_me[tag] = driver
            with self.driving_me[tag].lock:
                driver.driving_components.add(self)

        self.pininfo_sync()

    def disconnect_external_driver(self, tag: str):
        with self.lock:
            if self.driving_me[tag]:
                with self.driving_me[tag].lock:
                    # We should not KeyError, it is impossible.
                    # If it happens then we should catch it!
                    self.driving_me[tag].driving_components.remove(self)

                self.driving_me.pop(tag)

        self.pininfo_sync()

    def balance_pininfo(self, pininfos: list[PinInfo]):
        # THIS SHOULD NOT BE CALLED WITHOUT A LOCK!!
        pullups = []
        pulldowns = []

        for info in pininfos:
            if info.pinstate == PinStatus.PULLUP:
                pullups.append(
                    _normalize_resistance(info.resistance_ohms)
                )
            elif info.pinstate == PinStatus.PULLDOWN:
                pulldowns.append(
                    _normalize_resistance(info.resistance_ohms)
                )

        if not pullups and not pulldowns:
            self._update_balanced_pininfo(PinStatus.FLOATING, 0.0)
            return

        if pullups and not pulldowns:
            self._update_balanced_pininfo(
                PinStatus.PULLUP, _parallel_ohms(pullups)
            )
            return

        if pulldowns and not pullups:
            self._update_balanced_pininfo(
                PinStatus.PULLDOWN, _parallel_ohms(pulldowns)
            )
            return

        ru = _parallel_ohms(pullups)
        rd = _parallel_ohms(pulldowns)

        # Based on Cr50, it seems the chip's behavior to settle pin contention
        # is to follow the dominant puller.
        if (ru < 100) and (rd < 100):
            # This shouldn't happen. 100ohm vs 100ohm pin contention is
            # basically a short.
            prints.fatal(
                "extremely strong pin contention occured!! undefined behavior."
            )
            self._update_balanced_pininfo(PinStatus.FLOATING, 0.0)
        elif ru < rd:
            self._update_balanced_pininfo(PinStatus.PULLUP, ru)
        elif rd < ru:
            self._update_balanced_pininfo(PinStatus.PULLDOWN, rd)
        else:
            prints.fatal("ru == rd!! PinStatus set to FLOATING!!")
            self._update_balanced_pininfo(PinStatus.FLOATING, 0.0)

    def set_pininfo(self, pdpu: PinStatus, resistance: int | float):
        # This function is used to update the pd/pu on the pin
        # itself. If other components are driving us, then the updated value
        # would be in self.balanced_pininfo. But we need the device_pininfo
        # to track the pd/pu exerted on the chip, not influenced by the
        # balanced_pininfo.

        with self.lock:
            self.device_pininfo.pinstate = pdpu
            self.device_pininfo.resistance_ohms = round(float(resistance), 2)

        self.pininfo_sync()

    def mask_pininfo(self, en: bool):
        # A convenience function to mask the pininfo value. This is needed when
        # e.g. GPIO needs to disable a pin's output.
        with self.lock:
            self.mask_device_pininfo = en

        self.pininfo_sync()

    def read_pdpu(self) -> PinStatus:
        with self.lock:
            return self.balanced_pininfo.pinstate
    
    def read_resistance(self) -> float:
        with self.lock:
            return self.balanced_pininfo.resistance_ohms

    def pininfo_sync(self, visited: set | None = None):
        if visited is None:
            visited = set()
        if self in visited:
            return
        visited.add(self)

        # First, balance our own device PinInfo.
        with self.lock:
            # First, balance our own PinInfo with others that are driving us.
            pininfos = []
            for pindevice in self.driving_me.values():
                if not pindevice:
                    continue
                
                with pindevice.lock:
                    if not pindevice.mask_device_pininfo:
                        pininfos.append(pindevice.device_pininfo)
                    else:
                        pininfos.append(EMPTY_PININFO)

            if not self.mask_device_pininfo:
                pininfos.append(self.device_pininfo)
            else:
                pininfos.append(EMPTY_PININFO) 

            self.balance_pininfo(pininfos)

            # Snapshot driver targets so we can call them without the lock, else
            # we might deadlock.
            driving_components = list(self.driving_components)

        # Next, sync other pin's PinInfos.
        for driving_component in driving_components:
            driving_component.pininfo_sync(visited)

class Cr50Pinmux:
    def __init__(self):
        self.internal_pd = PinDevice()
        self.internal_pu = PinDevice()
        self.internal_pd.set_pininfo(PinStatus.PULLDOWN, 50000.0)
        self.internal_pu.set_pininfo(PinStatus.PULLUP, 50000.0)

        self.dioa: list[PinDevice] = []
        for _ in range(15):
            self.dioa.append(PinDevice())

        self.diob: list[PinDevice] = []
        for _ in range(8):
            self.diob.append(PinDevice())

        self.diom: list[PinDevice] = []
        for _ in range(5):
            self.diom.append(PinDevice())

        self.vio: list[PinDevice] = []
        for _ in range(2):
            self.vio.append(PinDevice())

        self.resetb: list[PinDevice] = []
        for _ in range(1):
            self.resetb.append(PinDevice())