# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import typing
import unicorn as qemu
import queue
import threading

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from .regdefs import GPIO_REGS
from lib.helpers import unhandled_register_exit

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

class GpioController:
    def __init__(self):
        self.opthread = None
        self.opqueue = queue.Queue()

        self.datain = 0

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

    def queue_write_datain_manual(self, bit: int):
        self.opqueue.put([self.datain_manual_write, (bit,)])

    def read_datain(self, size: int, queue: queue.Queue):
        queue.put(self.datain)
    
    def write_datain(self, size: int, value: int):
        return
    
    def datain_manual_write(self, bit: int):
        self.datain |= (1 << bit)

c_emu_0 = GpioController()
c_emu_0.start_worker()

c_emu_1 = GpioController()
c_emu_1.start_worker()

# Assert GPIO_BATT_PRES_L to allow CCD to be opened
c_emu_0.datain_manual_write(6)

# Assert GPIO_I2CP_SDA to signal that the I2C bus is idle, else the console
# gets spammed.
c_emu_0.queue_write_datain_manual(14)

# Assert GPIO_TPM_RST_L to signal that the AP is on.
c_emu_1.queue_write_datain_manual(0)

_REG_FUNC_MAP_0 = {
    GPIO_REGS["DATAIN"]: [c_emu_0.read_datain, c_emu_0.write_datain]
}

_REG_FUNC_MAP_1 = {
    GPIO_REGS["DATAIN"]: [c_emu_1.read_datain, c_emu_1.write_datain]
}

def component_read_handler_0(
    uc: qemu.Uc,
    offset: int,
    size: int,
    user_data: typing.Any,
) -> int:
    try:
        return c_emu_0.queue_read_worker_op(size, _REG_FUNC_MAP_0[offset][0])
    except KeyError:
        return 0

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
        return 0
    
def component_read_handler_1(
    uc: qemu.Uc,
    offset: int,
    size: int,
    user_data: typing.Any,
) -> int:
    try:
        return c_emu_1.queue_read_worker_op(size, _REG_FUNC_MAP_1[offset][0])
    except KeyError:
        return 0

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
        return 0