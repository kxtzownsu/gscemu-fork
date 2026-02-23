# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import typing
import unicorn as qemu
import queue
import threading

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from .regdefs import SPS_REGS
from lib.helpers import unhandled_register_exit

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

class SPISlaveDevice:
    def __init__(self):
        self.opthread = None
        self.opqueue = queue.Queue()

        self.miso_data = 0

        self.ictrl = {
            "CS_ASSERT": False,
            "CS_DEASSERT": False,
            "RXFIFO_OVERFLOW": False,
            "TXFIFO_EMPTY": False,
            "TXFIFO_FULL": False,
            "TXFIFO_LEVEL": False,
            "RXFIFO_LEVEL": False
        }

    def sps_worker(self):
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
            self.opthread = threading.Thread(target=self.sps_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn):
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()
        
    def queue_write_worker_op(self, size: int, value: int, target_fn):
        self.opqueue.put([target_fn, (size, value)])

    def read_dummy_word(self, size: int, queue: queue.Queue):
        # I don't think we can read from DUMMY_WORD, it's unclear.
        queue.put(0)
    
    def write_dummy_word(self, size: int, value: int):
        #print(f"MISO drive to {value}")
        self.miso_data = value

c_emu = SPISlaveDevice()
c_emu.start_worker()

_REG_FUNC_MAP = {
    SPS_REGS["DUMMY_WORD"]: [c_emu.read_dummy_word, c_emu.write_dummy_word],
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
        #unhandled_register_exit(g_uc(), ucthread(), prints, "SPS0", offset)
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
        #unhandled_register_exit(g_uc(), ucthread(), prints, "SPS0", offset)
        return 0