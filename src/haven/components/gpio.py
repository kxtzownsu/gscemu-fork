# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import typing
import unicorn as qemu
import queue
import threading

from lib.globalvars import *
from lib.pindevice import PinDevice, PinStatus
from env import *
from lib.logger import GscemuLogger
from .regdefs import GPIO_REGS
from lib.helpers import (
    unhandled_register_exit, 
    idx_regs_to_regmap,
    pattern_list_gen
)

from .m3 import pend_external_irq, unpend_external_irq

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

# PINMUX(DIOxx_SEL) = GPIOy_GPIOz_SEL
# Routes GPIO output to the external pad

# PINMUX(GPIOy_GPIOz_SEL) = DIOxx_SEL
# Routes external pad input into the GPIO input

GPIO_IRQS = [
    [
        pattern_list_gen(65, 16, 1), # GPIOxINT
        81 # GPIOCOMBINT
    ],
    [
        pattern_list_gen(82, 16, 1), # GPIOxINT
        98 # GPIOCOMBINT
    ],
]

class GpioController:
    def __init__(self, num: int):
        self.num = num

        self.irqnums = GPIO_IRQS[num]

        self.opthread = None
        self.opqueue = queue.Queue()

        # Create pinmux devices.
        self.pindevices: list[PinDevice] = []
        for idx in range(16):
            self.pindevices.append(
                PinDevice(
                    interrupt_fn=self.queue_pindevice_intr, 
                    interrupt_fn_userdata=idx
                )
            )

        # True = output, False = input(pd/pu disabled)
        self.gpio_output = [False] * 16

        # True = pu, False = pd/floating. 
        # Internal GPIO drive level, does not matter if gpio_output[pin] = False
        self.gpio_internal_levels = [False] * 16

        # Determined by gpio_output, gpio_internal_levels and the external
        # connected pin driving us.
        self.gpio_real_levels = [False] * 16

        # False = disabled, True = enabled
        self.gpio_interrupt = [False] * 16

        # We need to keep track of the pending interrupts for GPIO before we
        # can clear it. If this list is empty, then we can clear the comb GPIO
        # interrupt.
        self.gpio_pending_interrupts = [False] * 16
        self.gpio_pending_interrupts_is_edge = [False] * 16

        # False = low/high, True = falling/rising edge
        self.gpio_interrupt_type = [False] * 16

        # False = low/falling edge, True = high/rising edge
        self.gpio_interrupt_polarity = [False] * 16

    def _is_active_level_interrupt(self, bit: int) -> bool:
        if self.gpio_interrupt_polarity[bit]:
            return self.gpio_real_levels[bit]

        return not self.gpio_real_levels[bit]

    def _pend_pin_interrupt(self, bit: int, is_edge: bool):
        # Pend an interrupt for a pin.
        if self.gpio_pending_interrupts[bit]:
            return

        self.gpio_pending_interrupts[bit] = True
        self.gpio_pending_interrupts_is_edge[bit] = is_edge
        pend_external_irq(self.irqnums[0][bit])
        self.should_pend_combined_interrupt()

    def _clear_pin_interrupt(self, bit: int):
        # Clear a pending pin interrupt.
        if not self.gpio_pending_interrupts[bit]:
            return

        self.gpio_pending_interrupts[bit] = False
        self.gpio_pending_interrupts_is_edge[bit] = False
        unpend_external_irq(self.irqnums[0][bit])
        self.should_unpend_combined_interrupt()

    def _refresh_level_interrupt(self, bit: int):
        # Handle LOW/HIGH interrupts
        if not self.gpio_interrupt[bit] or self.gpio_interrupt_type[bit]:
            return

        # Once pending, keep it latched until the software clears it with
        # gpio_disable_interrupt and clrintstat
        if self.gpio_pending_interrupts[bit]:
            return

        if self._is_active_level_interrupt(bit):
            self._pend_pin_interrupt(bit, is_edge=False)

    def _handle_edge_transition(
        self,
        bit: int,
        old_level: bool,
        new_level: bool,
    ):
        if not self.gpio_interrupt[bit] or not self.gpio_interrupt_type[bit]:
            return

        if self.gpio_pending_interrupts[bit]:
            return

        if self.gpio_interrupt_polarity[bit]:
            has_edge = (not old_level) and new_level
        else:
            has_edge = old_level and (not new_level)

        if not has_edge:
            return

        self._pend_pin_interrupt(bit, is_edge=True)

    def gpio_worker(self):
        while True:
            try:
                op = self.opqueue.get()
                target_fn, args = op

                target_fn(*args)

                self.opqueue.task_done()

            except Exception as e:
                prints.fatal(e)

    def start_worker(self):
        if not self.opthread:
            self.opthread = threading.Thread(target=self.gpio_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn):
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()
        
    def queue_write_worker_op(self, size: int, value: int, target_fn):
        self.opqueue.put([target_fn, (size, value)])
        self.opqueue.join()

    def queue_pindevice_intr(
        self, 
        current_pinstate: PinStatus, 
        new_pinstate: PinStatus, 
        pin_number: int,
    ):
        self.opqueue.put(
            [
                self.pindevice_interrupt, 
                (current_pinstate, new_pinstate, pin_number)
            ]
        )

    def should_pend_combined_interrupt(self):
        if any(self.gpio_pending_interrupts):
            pend_external_irq(self.irqnums[1])

    def should_unpend_combined_interrupt(self):
        if not any(self.gpio_pending_interrupts):
            unpend_external_irq(self.irqnums[1])

    def pindevice_interrupt(
            self, 
            current_pinstate: PinStatus, 
            new_pinstate: PinStatus, 
            pin_number: int,
        ):
        # Called when the PinStatus changes, is not called if only the
        # resistance changes.
        old_level = self.gpio_real_levels[pin_number]
        new_level = False
        if new_pinstate == PinStatus.PULLUP:
            new_level = True

        self.gpio_real_levels[pin_number] = new_level

        self._handle_edge_transition(pin_number, old_level, new_level)
        self._refresh_level_interrupt(pin_number)

    def update_gpio_level(self, bit: int, state: int):
        pdpu = None
        if state:
            pdpu = PinStatus.PULLUP
            self.gpio_internal_levels[bit] = True
        else:
            pdpu = PinStatus.PULLDOWN
            self.gpio_internal_levels[bit] = False

        self.pindevices[bit].set_pininfo(pdpu, 10.0)

    def set_gpio_io(self, bit: int, io: bool):
        self.gpio_output[bit] = io
        self.pindevices[bit].mask_pininfo(not io)

    def read_datain(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            # Check if the bit is set in gpio_real_levels.
            if not self.gpio_real_levels[bit]:
                continue

            # Append the bit to val
            val |= (1 << bit)
                
        queue.put(val)
    
    def write_datain(self, size: int, value: int):
        for bit in range(16):
            self.update_gpio_level(
                bit, 
                (value & (1 << bit))
            )

    def read_dataout(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            # Check if the bit is set in gpio_internal_levels.
            if not self.gpio_internal_levels[bit]:
                continue

            # Append the bit to val
            val |= (1 << bit)
                
        queue.put(val)
    
    def write_dataout(self, size: int, value: int):
        for bit in range(16):
            self.update_gpio_level(
                bit, 
                (value & (1 << bit))
            )
    
    def read_masklowbyte(self, size: int, queue: queue.Queue, index: int):
        # index is the mask for bits [7:0]
        val = 0
        for bit in range(8):
            # Check if this bit is part of the mask.
            if not (index & (1 << bit)):
                continue
            
            # Check if the bit is set in gpio_internal_levels.
            if not self.gpio_internal_levels[bit]:
                continue
            
            # Append the bit to val
            val |= (1 << bit)

        queue.put(val)

    def write_masklowbyte(self, size: int, value: int, index: int):
        # index is the mask for bits [7:0]
        for bit in range(8):
            # Check if this bit is part of the mask.
            if not (index & (1 << bit)):
                continue
            
            self.update_gpio_level(
                bit, 
                bool(
                    (value & (1 << bit))
                )
            )

    def read_maskhighbyte(self, size: int, queue: queue.Queue, index: int):
        # index is the mask for bits [7:0]
        val = 0
        for bit in range(8):
            # Check if this bit is part of the mask.
            if not (index & (1 << bit)):
                continue

            # Check if the bit is set in gpio_internal_levels.
            if not self.gpio_internal_levels[bit + 8]:
                continue

            # Append the bit to val
            val |= (1 << (bit + 8))

        queue.put(val)

    def write_maskhighbyte(self, size: int, value: int, index: int):
        for bit in range(8):
            # Check if this bit is part of the mask.
            if not (index & (1 << bit)):
                continue

            self.update_gpio_level(
                bit + 8, 
                bool(
                    (value & (1 << bit + 8))
                )
            )

    def read_setdouten(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            # Check if the bit is set in gpio_output.
            if not self.gpio_output[bit]:
                continue

            # Append the bit to val
            val |= (1 << bit)

        queue.put(val)

    def write_setdouten(self, size: int, value: int):
        for bit in range(16):
            # Check if this bit is part of the mask.
            if not (value & (1 << bit)):
                continue

            self.set_gpio_io(bit, True)

    def read_clrdouten(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            # Check if the bit is set in gpio_output.
            if not self.gpio_output[bit]:
                continue

            # Append the bit to val
            val |= (1 << bit)

        queue.put(val)

    def write_clrdouten(self, size: int, value: int):
        for bit in range(16):
            # Check if this bit is part of the mask.
            if not (value & (1 << bit)):
                continue

            self.set_gpio_io(bit, False)

    def read_setinttype(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            # Check if the bit is set in gpio_interrupt_type.
            if not self.gpio_interrupt_type[bit]:
                continue

            # Append the bit to val
            val |= (1 << bit)

        queue.put(val)

    def write_setinttype(self, size: int, value: int):
        for bit in range(16):
            # Check if this bit is part of the mask.
            if not (value & (1 << bit)):
                continue

            self.gpio_interrupt_type[bit] = True

    def read_clrinttype(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            # Check if the bit is set in gpio_interrupt_type.
            if not self.gpio_interrupt_type[bit]:
                continue

            # Append the bit to val
            val |= (1 << bit)

        queue.put(val)

    def write_clrinttype(self, size: int, value: int):
        for bit in range(16):
            # Check if this bit is part of the mask.
            if not (value & (1 << bit)):
                continue

            self.gpio_interrupt_type[bit] = False
            self._refresh_level_interrupt(bit)

    def read_setintpol(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            # Check if the bit is set in gpio_interrupt_polarity.
            if not self.gpio_interrupt_polarity[bit]:
                continue

            # Append the bit to val
            val |= (1 << bit)

        queue.put(val)

    def write_setintpol(self, size: int, value: int):
        for bit in range(16):
            # Check if this bit is part of the mask.
            if not (value & (1 << bit)):
                continue

            self.gpio_interrupt_polarity[bit] = True
            self._refresh_level_interrupt(bit)

    def read_clrintpol(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            # Check if the bit is set in gpio_interrupt_polarity.
            if not self.gpio_interrupt_polarity[bit]:
                continue

            # Append the bit to val
            val |= (1 << bit)

        queue.put(val)

    def write_clrintpol(self, size: int, value: int):
        for bit in range(16):
            # Check if this bit is part of the mask.
            if not (value & (1 << bit)):
                continue

            self.gpio_interrupt_polarity[bit] = False
            self._refresh_level_interrupt(bit)

    def read_setinten(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            # Check if the bit is set in gpio_interrupt.
            if not self.gpio_interrupt[bit]:
                continue

            # Append the bit to val
            val |= (1 << bit)

        queue.put(val)

    def write_setinten(self, size: int, value: int):
        for bit in range(16):
            # Check if this bit is part of the mask.
            if not (value & (1 << bit)):
                continue

            # Are interrupts disabled
            if self.gpio_interrupt[bit]:
                continue # Interrupts enabled

            self.gpio_interrupt[bit] = True
            self._refresh_level_interrupt(bit)

    def read_clrinten(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            # Check if the bit is set in gpio_interrupt.
            if not self.gpio_interrupt[bit]:
                continue

            # Append the bit to val
            val |= (1 << bit)

        queue.put(val)

    def write_clrinten(self, size: int, value: int):
        for bit in range(16):
            # Check if this bit is part of the mask.
            if not (value & (1 << bit)):
                continue
            
            # Interrupts enabled
            if not self.gpio_interrupt[bit]:
                continue # Interrupts not enabled

            self.gpio_interrupt[bit] = False

    def read_clrintstat(self, size: int, queue: queue.Queue):
        val = 0
        for bit in range(16):
            # Check if the bit is set in gpio_pending_interrupts.
            if not self.gpio_pending_interrupts[bit]:
                continue

            # Append the bit to val
            val |= (1 << bit)

        queue.put(val)

    def write_clrintstat(self, size: int, value: int):
        for bit in range(16):
            # Check if this bit is part of the mask.
            if not (value & (1 << bit)):
                continue

            keep_pending = (
                self.gpio_interrupt[bit]
                and not self.gpio_interrupt_type[bit]
                and self._is_active_level_interrupt(bit)
            )

            if keep_pending:
                if not self.gpio_pending_interrupts[bit]:
                    self._pend_pin_interrupt(bit, is_edge=False)
            else:
                self._clear_pin_interrupt(bit)

    def datain_manual_write(self, bit: int, state: bool):
        self.update_gpio_level(bit, state)

c_emu_0 = GpioController(0)
c_emu_0.start_worker()

c_emu_1 = GpioController(1)
c_emu_1.start_worker()

_REG_FUNC_MAP_0 = {
    GPIO_REGS["DATAIN"]: [c_emu_0.read_datain, c_emu_0.write_datain],
    GPIO_REGS["DATAOUT"]: [c_emu_0.read_dataout, c_emu_0.write_dataout],

    GPIO_REGS["SETDOUTEN"]: [c_emu_0.read_setdouten, c_emu_0.write_setdouten],
    GPIO_REGS["CLRDOUTEN"]: [c_emu_0.read_clrdouten, c_emu_0.write_clrdouten],

    GPIO_REGS["SETINTEN"]: [c_emu_0.read_setinten, c_emu_0.write_setinten],
    GPIO_REGS["CLRINTEN"]: [c_emu_0.read_clrinten, c_emu_0.write_clrinten],

    GPIO_REGS["SETINTTYPE"]: [
        c_emu_0.read_setinttype, c_emu_0.write_setinttype
    ],
    GPIO_REGS["CLRINTTYPE"]: [
        c_emu_0.read_clrinttype, c_emu_0.write_clrinttype
    ],

    GPIO_REGS["SETINTPOL"]: [c_emu_0.read_setintpol, c_emu_0.write_setintpol],
    GPIO_REGS["CLRINTPOL"]: [c_emu_0.read_clrintpol, c_emu_0.write_clrintpol],
    
    GPIO_REGS["CLRINTSTAT"]: [
        c_emu_0.read_clrintstat, c_emu_0.write_clrintstat
    ],
}

_REG_FUNC_MAP_1 = {
    GPIO_REGS["DATAIN"]: [c_emu_1.read_datain, c_emu_1.write_datain],
    GPIO_REGS["DATAOUT"]: [c_emu_1.read_dataout, c_emu_1.write_dataout],

    GPIO_REGS["SETDOUTEN"]: [c_emu_1.read_setdouten, c_emu_1.write_setdouten],
    GPIO_REGS["CLRDOUTEN"]: [c_emu_1.read_clrdouten, c_emu_1.write_clrdouten],

    GPIO_REGS["SETINTEN"]: [c_emu_1.read_setinten, c_emu_1.write_setinten],
    GPIO_REGS["CLRINTEN"]: [c_emu_1.read_clrinten, c_emu_1.write_clrinten],

    GPIO_REGS["SETINTTYPE"]: [
        c_emu_1.read_setinttype, c_emu_1.write_setinttype
    ],
    GPIO_REGS["CLRINTTYPE"]: [
        c_emu_1.read_clrinttype, c_emu_1.write_clrinttype
    ],

    GPIO_REGS["SETINTPOL"]: [c_emu_1.read_setintpol, c_emu_1.write_setintpol],
    GPIO_REGS["CLRINTPOL"]: [c_emu_1.read_clrintpol, c_emu_1.write_clrintpol],

    GPIO_REGS["CLRINTSTAT"]: [
        c_emu_1.read_clrintstat, c_emu_1.write_clrintstat
    ],
}

idx_regs_to_regmap(
    _REG_FUNC_MAP_0, GPIO_REGS["MASKLOWBYTE"],
    c_emu_0.read_masklowbyte, c_emu_0.write_masklowbyte
)

idx_regs_to_regmap(
    _REG_FUNC_MAP_0, GPIO_REGS["MASKHIGHBYTE"],
    c_emu_0.read_maskhighbyte, c_emu_0.write_maskhighbyte
)

idx_regs_to_regmap(
    _REG_FUNC_MAP_1, GPIO_REGS["MASKLOWBYTE"],
    c_emu_1.read_masklowbyte, c_emu_1.write_masklowbyte
)

idx_regs_to_regmap(
    _REG_FUNC_MAP_1, GPIO_REGS["MASKHIGHBYTE"],
    c_emu_1.read_maskhighbyte, c_emu_1.write_maskhighbyte
)

def component_read_handler_0(
    uc: qemu.Uc,
    offset: int,
    size: int,
    user_data: typing.Any,
) -> int:
    try:
        return c_emu_0.queue_read_worker_op(size, _REG_FUNC_MAP_0[offset][0])
    except KeyError:
        unhandled_register_exit(g_uc(), ucthread(), prints, "GPIO0", offset)

def component_write_handler_0(
    uc: qemu.Uc,
    offset: int,
    size: int,
    value: int,
    user_data: typing.Any,
) -> None:
    try:
        c_emu_0.queue_write_worker_op(size, value, _REG_FUNC_MAP_0[offset][1])
    except KeyError:
        unhandled_register_exit(g_uc(), ucthread(), prints, "GPIO0", offset)
    
def component_read_handler_1(
    uc: qemu.Uc,
    offset: int,
    size: int,
    user_data: typing.Any,
) -> int:
    try:
        return c_emu_1.queue_read_worker_op(size, _REG_FUNC_MAP_1[offset][0])
    except KeyError:
        unhandled_register_exit(g_uc(), ucthread(), prints, "GPIO1", offset)

def component_write_handler_1(
    uc: qemu.Uc,
    offset: int,
    size: int,
    value: int,
    user_data: typing.Any,
) -> None:
    try:
        c_emu_1.queue_write_worker_op(size, value, _REG_FUNC_MAP_1[offset][1])
    except KeyError:
        unhandled_register_exit(g_uc(), ucthread(), prints, "GPIO1", offset)