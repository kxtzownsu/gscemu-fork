# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer
"""Cr50 main timer component."""

import typing
import unicorn as qemu
import queue
import threading

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from src.emulators.haven.registers import TIMELS_REGS
from lib.helpers import unhandled_register_exit, args_lambda_gen

from src.components.m3 import pend_external_irq

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

# The plan for the LSTimer is that we are able to create a seperate thread that 
# uses a threading.Event with a timeout, and after X seconds, if the signal
# is not triggered to stop the timeout, and the timer times out, then we can
# send an interrupt trigger to the M3 to tell it that the timer has hit the
# timeout.

class LowSpeedTimer:
    def __init__(self):
        self.opthread = None
        self.opqueue = queue.Queue()

        self.countdown_thread = None
        self.countdown_event = threading.Event()

        self.timer_state = [
            {
                "CONTROL": 0,
                "LOAD": 0,
                "RELOADVAL": 0,
                "VALUE": 0,
                "IER": 0,
                "ISR": 0,
                "IAR": 0,
                "WAKEUP_ACK": 0,
            } for _ in range(2)
        ]

    def timels_worker(self):
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
            self.opthread = threading.Thread(target=self.timels_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn) -> None:
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()
        
    def queue_write_worker_op(self, size: int, value: int, target_fn) -> None:
        self.opqueue.put([target_fn, (size, value)])

    def countdown_worker(self, timeout_num: int|float, irq: int) -> None:
        did_timer_hit = self.countdown_event.wait(timeout=timeout_num)

        if not did_timer_hit:
            # The main thread is telling us to kill the worker.
            return
        
        # If we reached here, it means the timer hit 0. Pend an external
        # interrupt on the M3.
        pend_external_irq(irq)

    def pend_countdown_worker(self, timeout_num: int|float, irq: int) -> None:
        if self.countdown_thread:
            # Just assume the old thread would be thrown away after this, and
            # we don't have to handle anything.
            self.countdown_event.set()
        
        self.countdown_thread = threading.Thread(
            target=self.countdown_worker, args=(timeout_num, irq)
        )
        self.countdown_thread.daemon = True
        self.countdown_thread.start()

    def kill_countdown_worker(self) -> bool:
        if not self.countdown_thread:
            return
        
        self.countdown_event.set()
        self.countdown_thread = None

    def read_timer_control(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(self.timer_state[index]["CONTROL"])

    def write_timer_control(
        self, size: int, value: int, index: int
    ) -> None:
        self.timer_state[index]["CONTROL"] = value

    def read_timer_load(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(self.timer_state[index]["LOAD"])

    def write_timer_load(
        self, size: int, value: int, index: int
    ) -> None:
        self.timer_state[index]["LOAD"] = value

    def read_timer_reloadval(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(self.timer_state[index]["RELOADVAL"])

    def write_timer_reloadval(
        self, size: int, value: int, index: int
    ) -> None:
        self.timer_state[index]["RELOADVAL"] = value

    def read_timer_value(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(self.timer_state[index]["VALUE"])

    def write_timer_value(
        self, size: int, value: int, index: int
    ) -> None:
        self.timer_state[index]["VALUE"] = value

    def read_timer_ier(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(self.timer_state[index]["IER"])

    def write_timer_ier(
        self, size: int, value: int, index: int
    ) -> None:
        self.timer_state[index]["IER"] = value

    def read_timer_isr(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(self.timer_state[index]["ISR"])

    def write_timer_isr(
        self, size: int, value: int, index: int
    ) -> None:
        self.timer_state[index]["ISR"] = value

    def read_timer_iar(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(self.timer_state[index]["IAR"])

    def write_timer_iar(
        self, size: int, value: int, index: int
    ) -> None:
        self.timer_state[index]["IAR"] = value

    def read_timer_wakeup_ack(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(self.timer_state[index]["WAKEUP_ACK"])

    def write_timer_wakeup_ack(
        self, size: int, value: int, index: int
    ) -> None:
        self.timer_state[index]["WAKEUP_ACK"] = value

c_emu = LowSpeedTimer()
c_emu.start_worker()

# Within a TIMELS component, there are 2 timers that do the same thing.
# TIMER0 and TIMER1.
_SUB_TIMER_FUNC_MAP = {
    TIMELS_REGS["TIMER"]["CONTROL"]: [
        c_emu.read_timer_control, c_emu.write_timer_control
    ],
    TIMELS_REGS["TIMER"]["LOAD"]: [
        c_emu.read_timer_load, c_emu.write_timer_load
    ],
    TIMELS_REGS["TIMER"]["RELOADVAL"]: [
        c_emu.read_timer_reloadval, c_emu.write_timer_reloadval
    ],
    TIMELS_REGS["TIMER"]["VALUE"]: [
        c_emu.read_timer_value, c_emu.write_timer_value
    ],
    TIMELS_REGS["TIMER"]["IER"]: [
        c_emu.read_timer_ier, c_emu.write_timer_ier
    ],
    TIMELS_REGS["TIMER"]["ISR"]: [
        c_emu.read_timer_isr, c_emu.write_timer_isr
    ],
    TIMELS_REGS["TIMER"]["IAR"]: [
        c_emu.read_timer_iar, c_emu.write_timer_iar
    ],
    TIMELS_REGS["TIMER"]["WAKEUP_ACK"]: [
        c_emu.read_timer_wakeup_ack, c_emu.write_timer_wakeup_ack
    ],  
}

_REG_FUNC_MAP = {}

for timer_idx in range(2):
    for offset, fn_map in _SUB_TIMER_FUNC_MAP.items():
        _REG_FUNC_MAP[TIMELS_REGS[
            f"TIMER{timer_idx}_BASE"
        ] + offset] = [
            args_lambda_gen(fn_map[0], timer_idx),
            args_lambda_gen(fn_map[1], timer_idx)
        ]

def component_read_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    user_data: typing.Any,
) -> int:
    try:
        return c_emu.queue_read_worker_op(size, _REG_FUNC_MAP[offset][0])
    except KeyError:
        unhandled_register_exit(g_uc(), ucthread(), prints, "TIMELS0", offset)

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
        unhandled_register_exit(g_uc(), ucthread(), prints, "TIMELS0", offset)