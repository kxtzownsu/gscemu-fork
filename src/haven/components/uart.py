# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

import queue
import threading
import typing

import unicorn as qemu

from env import *
from lib.emulator_context import ComponentObjects, EmulatorContext
from lib.helpers import (
    extract_max_number,
    unhandled_register_exit,
    unhandled_register_io,
)
from lib.logger import GscemuLogger

from .m3 import pend_external_irq, unpend_external_irq

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


class UartController:
    def __init__(self, ctx: EmulatorContext):
        self.ctx = ctx

        self.opthread = None
        self.opqueue = queue.Queue()

        self.input_queue = queue.Queue()

        # Have a blank function incase that the callback was never actually
        # initialized.
        self.char_out_callback = lambda char: None
        self.char_out_callback_userdata = None

        # TX cannot be ready until CTRL is set. CTRL is 0 by default.
        self.state = 1  # BIT(0)

        self.ctrl = 0
        self.nco = 0
        self.fifo = 0
        self.ictrl = 0

    def uart_worker(self):
        while True:
            try:
                # Wait for the next operation to enter the queue
                target_fn, args = self.opqueue.get()

                # update STATE based on input queue
                if self.input_queue.empty():
                    self.state |= 128  # BIT(7), True
                else:
                    self.state &= ~128  # BIT(7), False
                    pend_external_irq(self.ctx.c_fast.m3, 174)

                if target_fn:
                    target_fn(*args)  # Splat the arguments into the target_fn

                # For write operations, this doesn't do anything. For read
                # operations, we need to tell the handler that we have processed
                # the value, and execution can proceed.
                self.opqueue.task_done()

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

    def set_char_out_callback(self, fn, user_data) -> None:
        self.char_out_callback = fn
        self.char_out_callback_userdata = user_data

    def queued_uart_input(self, input: int) -> None:
        self.input_queue.put(input, block=False)
        self.opqueue.put([None, tuple()])

    def queued_uart_out_callback(self, fn, user_data) -> None:
        self.opqueue.put([self.set_char_out_callback, (fn, user_data)])

    def ctrl_process(self):
        # UART_CTRL_TX
        # 0 = disabled, 1 = enabled
        if self.ctrl & 1:  # BIT(0)
            # UART_STATE_TX
            # 0 = enabled, 1 = busy
            self.state &= ~1  # BIT(0)

            # UART_STATE_TX_EMPTY
            # 0 = not empty, 1 = empty
            self.state |= 16  # BIT(4)

            # UART_STATE_TX_IDLE
            # 0 = not idle, 1 = idle
            self.state |= 32  # BIT(5)

        # UART_CTRL_RX
        # 0 = disabled, 1 = enabled
        if self.ctrl & 2:  # BIT(1)
            # UART_STATE_RX
            # 0 = enabled, 1 = busy
            self.state &= ~2  # BIT(1)

            # UART_STATE_RX_EMPTY
            # 0 = not empty, 1 = empty
            self.state |= 128  # BIT(7)

            # UART_STATE_RX_IDLE
            # 0 = not idle, 1 = idle
            self.state |= 64  # BIT(6)

    def read_wdata(self, size: int, queue: queue.Queue) -> None:
        unhandled_register_io(prints, "READ", "UART0", "WDATA")
        queue.put(0)

    def write_wdata(self, size: int, value: int) -> None:
        if not (self.state & 1):  # BIT(0)
            self.char_out_callback(value, self.char_out_callback_userdata)
        else:
            prints.warning("WDATA written to whilst STATE_TX set!")

    def read_rdata(self, size: int, queue: queue.Queue) -> None:
        if not (self.state & 2):  # BIT(1)
            try:
                char = self.input_queue.get_nowait()
            except queue.Empty:
                prints.warning("RDATA read when no available chars!")
                char = 0

            queue.put(char)
        else:
            prints.warning("RDATA written to whilst STATE_RX set!")

    def write_rdata(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "UART0", "RDATA")

    def read_nco(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.nco)

    def write_nco(self, size: int, value: int) -> None:
        self.nco = value

    def read_ctrl(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.ctrl)

    def write_ctrl(self, size: int, value: int) -> None:
        self.ctrl = value

        if self.ctrl:
            self.ctrl_process()

    def read_state(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.state)

    def write_state(self, size: int, value: int) -> None:
        self.state = value

    def read_fifo(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.fifo)

    def write_fifo(self, size: int, value: int) -> None:
        self.fifo = value

    def read_ictrl(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.ictrl)

    def write_ictrl(self, size: int, value: int) -> None:
        self.ictrl = value

    def read_istateclr(self, size: int, queue: queue.Queue) -> None:
        unhandled_register_io(prints, "READ", "UART0", "ISTATECLR")
        queue.put(0)

    def write_istateclr(self, size: int, value: int) -> None:
        if value & 1:
            # TX_INT
            unpend_external_irq(self.ctx.c_fast.m3, 177)

        if value & 2:
            # RX_INT
            unpend_external_irq(self.ctx.c_fast.m3, 174)


def init_UartController(ctx: EmulatorContext, regs: dict):
    c_emu = UartController(ctx)
    c_emu.start_worker()

    reg_fn_map = [0] * (extract_max_number(regs) + 4)

    reg_fn_map[regs["WDATA"]] = [c_emu.read_wdata, c_emu.write_wdata]
    reg_fn_map[regs["NCO"]] = [c_emu.read_nco, c_emu.write_nco]
    reg_fn_map[regs["CTRL"]] = [c_emu.read_ctrl, c_emu.write_ctrl]
    reg_fn_map[regs["STATE"]] = [c_emu.read_state, c_emu.write_state]
    reg_fn_map[regs["RDATA"]] = [c_emu.read_rdata, c_emu.write_rdata]
    reg_fn_map[regs["FIFO"]] = [c_emu.read_fifo, c_emu.write_fifo]
    reg_fn_map[regs["ICTRL"]] = [c_emu.read_ictrl, c_emu.write_ictrl]
    reg_fn_map[regs["ISTATECLR"]] = [
        c_emu.read_istateclr,
        c_emu.write_istateclr,
    ]

    def component_read_handler(
        uc: qemu.Uc,
        offset: int,
        size: int,
        user_data: typing.Any,
    ) -> int:
        try:
            return c_emu.queue_read_worker_op(size, reg_fn_map[offset][0])
        except KeyError:
            unhandled_register_exit(ctx, prints, "UART0", offset)

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
            unhandled_register_exit(ctx, prints, "UART0", offset)

    return ComponentObjects(
        c_emu, component_read_handler, component_write_handler
    )


def cr50_uart_input(c_emu: UartController, unicode_char_code: int) -> None:
    c_emu.queued_uart_input(unicode_char_code)


def cr50_uart_output_callback(c_emu: UartController, fn, user_data) -> None:
    c_emu.queued_uart_out_callback(fn, user_data)
