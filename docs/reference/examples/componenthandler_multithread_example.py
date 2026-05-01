# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer
"""Example component handler"""

import typing
import unicorn as qemu
import queue
import threading

from lib.emulator_context import EmulatorContext, ComponentObjects
from env import *
from lib.logger import GscemuLogger
from lib.helpers import unhandled_register_exit

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


class ComponentXX:
    def __init__(self):
        self.opthread = None
        self.opqueue = queue.Queue()

        self.xy = 0

    def xx_worker(self):
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


def init_ComponentXX(ctx: EmulatorContext, regs: dict):
    c_emu = ComponentXX()
    c_emu.start_worker()

    reg_fn_map = {
        regs["XY_PART"]: [c_emu.read_xy, c_emu.write_xy]
    }

    def component_read_handler(
        uc: qemu.Uc,
        offset: int,
        size: int,
        user_data: typing.Any,
    ) -> int:
        try:
            return c_emu.queue_read_worker_op(size, reg_fn_map[offset][0])
        except KeyError:
            unhandled_register_exit(ctx, prints, "XX", offset)

    def component_write_handler(
        uc: qemu.Uc,
        offset: int,
        size: int,
        value: int,
        user_data: typing.Any,
    ) -> None:
        try:
            c_emu.queue_write_worker_op(size, value, reg_fn_map[offset][1])
        except KeyError:
            unhandled_register_exit(ctx, prints, "XX", offset)

    return ComponentObjects(
        c_emu, component_read_handler, component_write_handler
    )
