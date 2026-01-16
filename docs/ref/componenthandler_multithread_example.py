# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer
"""Example component handler"""

import typing
import unicorn as qemu
import queue
import threading

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from src.emulators.haven.registers import XX_REGS
from lib.helpers import unhandled_register_exit

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

class ComponentXX:
    def __init__(self):
        self.opthread = None
        self.opthread = queue.Queue()

    def xx_worker(self):
        while True:
            try:
                op = self.opthread.get()
                target_fn, args = op

                target_fn(*args)

            except Exception as e:
                prints.fatal(e)

    def start_worker(self):
        if not self.opthread:
            self.opthread = threading.Thread(target=self.xx_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn):
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()
        
    def queue_write_worker_op(self, size: int, value: int, target_fn):
        self.opqueue.put([target_fn, (size, value)])

    def read_xy(self, size: int, queue: queue.Queue):
        queue.put(self.xy)
    
    def write_xy(self, size: int, value: int):
        self.xy = value

c_emu = ComponentXX()

_REG_FUNC_MAP = {
    XX_REGS["XY_PART"]: [c_emu.read_xy, c_emu.write_xy]
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
        unhandled_register_exit(prints, "XX", offset)

def component_write_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    value: int,
    user_data: typing.Any,
) -> None:
    try:
        c_emu.queue_read_worker_op(size, value, _REG_FUNC_MAP[offset][1])
    except KeyError:
        unhandled_register_exit(prints, "XX", offset)