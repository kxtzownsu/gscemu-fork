# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

# run with python3 -m tests.pinmux_test

import termcolor
from src.haven.components.pinmux import PinDevice, PinStatus

def test_single_pin():
    diob4 = PinDevice()
    diob4.set_pininfo(PinStatus.PULLUP, 1000.0)

    return (
        (diob4.read_resistance() == 1000.0)
        and (diob4.read_pdpu() == PinStatus.PULLUP)
    )

def test_pin_masking():
    diob4 = PinDevice()
    diob4.set_pininfo(PinStatus.PULLUP, 1000.0)

    cond1 = (
        (diob4.read_resistance() == 1000.0) 
        and (diob4.read_pdpu() == PinStatus.PULLUP)
    )

    diob4.mask_pininfo(True)

    cond2 = (
        (diob4.read_resistance() == 0.0) 
        and (diob4.read_pdpu() == PinStatus.FLOATING)
    )

    diob4.mask_pininfo(False)

    cond3 = (
        (diob4.read_resistance() == 1000.0) 
        and (diob4.read_pdpu() == PinStatus.PULLUP)
    )

    return (cond1 and cond2 and cond3)

def test_pin_contention():
    # The Cr50 behavior is to just return the pd/pu that has the least
    # resistance. Although, not sure what actually happens on the silicon
    # when theres a PU on one side and PD on another.
    
    gpio0_1 = PinDevice()
    diob4 = PinDevice()

    gpio0_1.drive_by_component(diob4)
    diob4.drive_by_component(gpio0_1)

    diob4.set_pininfo(PinStatus.PULLUP, 1500.0)
    gpio0_1.set_pininfo(PinStatus.PULLDOWN, 1000.0)
    
    return (
        (gpio0_1.read_resistance() == 1000.0) 
        and (gpio0_1.read_pdpu() == PinStatus.PULLDOWN)
        and (diob4.read_resistance() == 1000.0)
        and (diob4.read_pdpu() == PinStatus.PULLDOWN)
    )

def test_combined_resistance():    
    # Following the 1/R + 1/R = 1/combined R rule,
    # 1/15 + 1/10 = 1/6, so our resistance is 6ohms.
    gpio0_1 = PinDevice()
    diob4 = PinDevice()

    gpio0_1.drive_by_component(diob4)
    diob4.drive_by_component(gpio0_1)

    diob4.set_pininfo(PinStatus.PULLUP, 1500.0)
    gpio0_1.set_pininfo(PinStatus.PULLUP, 1000.0)
    
    return (
        (gpio0_1.read_resistance() == 600.0) 
        and (gpio0_1.read_pdpu() == PinStatus.PULLUP)
        and (diob4.read_resistance() == 600.0)
        and (diob4.read_pdpu() == PinStatus.PULLUP)
    )

def test_chained_devices():
    # A more advanced version of pin contention which involves a looped chain
    # of devices too in a way.
    # gpio0_2 pd drives gpio0_1 pd, so no pin contention, 1/13 + 1/10 = 1/5.65, so gpio0_1 exp=5.65 pd
    # gpio0_1 pd drives diob4 pu, so pin contention occurs, so diob4 exp=10.0 pd
    # diob4 pu drives gpio0_2 pd, so pin contention occurs, so gpio0_2 exp=13.0 pd

    gpio0_1 = PinDevice()
    diob4 = PinDevice()
    gpio0_2 = PinDevice()

    # Matching Cr50 sematics of PINDEVICEx_SEL = PINDEVICEy_NUM where the SEL
    # register sets the driver for that PinDevice.
    diob4.drive_by_component(gpio0_1)
    gpio0_2.drive_by_component(diob4)
    gpio0_1.drive_by_component(gpio0_2)

    diob4.set_pininfo(PinStatus.PULLUP, 1500.0)
    gpio0_1.set_pininfo(PinStatus.PULLDOWN, 1000.0)
    gpio0_2.set_pininfo(PinStatus.PULLDOWN, 1300.0)

    return (
        (gpio0_1.read_resistance() == 565.22)
        and (gpio0_2.read_resistance() == 1300.0)
        and (diob4.read_resistance() == 1000.0)
    )


TESTS = {
    "single_pin": test_single_pin,
    "pin_masking": test_pin_masking,
    "pin_contention": test_pin_contention,
    "combined_resistance": test_combined_resistance,
    "chained_devices_pin_contention": test_chained_devices,
}

for testname, testfn in TESTS.items():
    result = testfn()

    if result:
        print(f"{testname} {termcolor.colored("passed", "green")}")
    else:
        print(f"{testname} {termcolor.colored("failed", "red")}")