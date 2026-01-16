# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import typing
import unicorn as qemu
import queue
import threading
import sys

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from src.emulators.haven.registers import UART_REGS
from lib.helpers import unhandled_register_exit, unhandled_register_io

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

class UartController:
    def __init__(self):
        self.opthread = None
        self.opqueue = queue.Queue()

        self.input_queue = queue.Queue()

        # TX cannot be ready until CTRL is set. CTRL is 0 by default.
        self.state = 1 # BIT(0)

        self.ctrl = 0
        self.nco = 0

    def uart_worker(self):
        while True:
            try:
                # Wait for the next operation to enter the queue
                target_fn, args = self.opqueue.get()

                # update STATE based on input queue
                if self.input_queue.empty():
                    self.state |= 128 # BIT(7), True
                else:
                    self.state &= ~128 # BIT(7), False

                target_fn(*args) # Splat the arguments into the target_fn

                # For write operations, this doesn't do anything. For read
                # operations, we need to tell the handler that we have processed
                # the value, and execution can proceed.
                self.opqueue.task_done()

                # After every operation, we might need to also adjust other
                # register values.

                # UART_CTRL_TX
                # 0 = disabled, 1 = enabled
                if self.ctrl & 1: # BIT(0)
                    # UART_STATE_TX
                    # 0 = enabled, 1 = busy
                    self.state &= ~1 # BIT(0)

                    # UART_STATE_TX_EMPTY
                    # 0 = not empty, 1 = empty
                    self.state |= 16 # BIT(4)

                    # UART_STATE_TX_IDLE
                    # 0 = not idle, 1 = idle
                    self.state |= 32 # BIT(5)

            except Exception as e:
                prints.fatal(e)

    def start_worker(self):
        if not self.opthread:
            self.opthread = threading.Thread(target=self.uart_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn):
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()
        
    def queue_write_worker_op(self, size: int, value: int, target_fn):
        self.opqueue.put([target_fn, (size, value)])

    def read_wdata(self, size: int, queue: queue.Queue) -> None:
        unhandled_register_io(prints, "READ", "UART0", "WDATA")
        queue.put(0)

    def write_wdata(self, size: int, value: int) -> None:
        if not (self.state & 1): # BIT(0)
            try:
                sys.stdout.write(chr(value))
                sys.stdout.flush()
            except:
                pass
        else:
            prints.warning("WDATA written to whilst STATE TX busy set!")

    def read_nco(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.nco)

    def write_nco(self, size: int, value: int) -> None:
        self.nco = value

    def read_ctrl(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.ctrl)

    def write_ctrl(self, size: int, value: int) -> None:
        self.ctrl = value

    def read_state(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.state)

    def write_state(self, size: int, value: int) -> None:
        self.state = value

    def read_rdata(self, size: int, queue: queue.Queue) -> None:
        try:
            char = self.input_queue.get_nowait()
        except queue.Empty:
            prints.warning("RDATA read when no available chars!")
            char = 0

        queue.put(char)

    def write_rdata(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "UART0", "RDATA")

c_emu = UartController()
c_emu.start_worker()

_REG_FUNC_MAP = {
    UART_REGS["WDATA"]: [c_emu.read_wdata, c_emu.write_wdata],
    UART_REGS["NCO"]: [c_emu.read_nco, c_emu.write_nco],
    UART_REGS["CTRL"]: [c_emu.read_ctrl, c_emu.write_ctrl],
    UART_REGS["STATE"]: [c_emu.read_state, c_emu.write_state],
    UART_REGS["RDATA"]: [c_emu.read_rdata, c_emu.write_rdata],
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
        unhandled_register_exit(prints, "UART0", offset)

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
        unhandled_register_exit(prints, "UART0", offset)