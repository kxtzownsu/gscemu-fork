# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import typing
import unicorn as qemu
import queue
import threading

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from .regdefs import USB_REGS
from lib.helpers import unhandled_register_exit

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

class UsbController:
    def __init__(self):
        self.opthread = None
        self.opqueue = queue.Queue()

        self.grstctl = 0

    def usb_worker(self):
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
            self.opthread = threading.Thread(target=self.usb_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn):
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()
        
    def queue_write_worker_op(self, size: int, value: int, target_fn):
        self.opqueue.put([target_fn, (size, value)])

    def read_grstctl(self, size: int, queue: queue.Queue):
        queue.put(self.grstctl)
    
    def write_grstctl(self, size: int, value: int):
        return

c_emu = UsbController()
c_emu.start_worker()

_REG_FUNC_MAP = {
    USB_REGS["GRSTCTL"]: [c_emu.read_grstctl, c_emu.write_grstctl]
}

def component_read_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    user_data: typing.Any,
) -> int:
    try:
        return c_emu.queue_read_worker_op(size, _REG_FUNC_MAP[offset][0])
    except KeyError:
        return 0

def component_write_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    value: int,
    user_data: typing.Any,
) -> None:
    try:
        c_emu.queue_write_worker_op(size, value, _REG_FUNC_MAP[offset][1])
    except KeyError:
        return 0