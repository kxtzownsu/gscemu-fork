# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer
"""Cr50 main timer component.

This component was vibecoded, a rewrite is needed as the vibecoded version does
not have accurate enough ticks, and honestly this is overall a bad way to go
around it.
"""

import typing
import time
import unicorn as qemu
import queue
import threading

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from ..registers import TIMELS_REGS
from lib.helpers import unhandled_register_exit, args_lambda_gen
from .m3 import pend_external_irq

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

TIMER_FREQ_HZ = 8 * 32768
NS_PER_TICK = 1_000_000_000 / TIMER_FREQ_HZ
TIMER_IRQS = [159, 160]

class TimerState:
    """State for a single timer within the TIMELS peripheral."""

    def __init__(self, timer_index: int):
        self.index = timer_index
        self.irq = TIMER_IRQS[timer_index]

        # Registers
        self.control = 0
        self.status = 0  # Bit 0: WRAPPED
        self.load = 0
        self.reloadval = 0xFFFFFFFF
        self.step = 0
        self.ier = 0  # Interrupt Enable
        self.isr = 0  # Interrupt Status
        self.ipr = 0  # Interrupt Pending
        self.iar = 0  # Interrupt Acknowledge
        self.wakeup_ack = 0

        # Runtime state for countdown tracking
        self.start_time_ns = 0  # perf_counter_ns when timer started
        self.start_value = 0  # VALUE when timer started
        self.running = False

# The plan for the TIMELS component is that we are able to create a seperate 
# thread that uses a threading.Event with a timeout, and after X seconds, if the
# signal is not triggered to stop the timeout, and the timer times out, then we 
# can send an interrupt trigger to the M3 to tell it that the timer has hit the
# timeout.

class LowSpeedTimer:
    """TIMELS peripheral emulation with two countdown timers.

    This emulator uses high-resolution timing to simulate the timer countdown.
    Instead of actually decrementing a counter, we record the start time and
    compute the elapsed ticks on each VALUE read. This provides accurate
    timing without CPU overhead.

    A separate watchdog thread monitors running timers and triggers interrupts
    when they expire.
    """

    def __init__(self):
        self.opthread = None
        self.opqueue = queue.Queue()

        self.watchdog_thread = None
        self.watchdog_stop = threading.Event()
        self.watchdog_check = threading.Event()

        self.timer_lock = threading.Lock()

        self.timers = [TimerState(0), TimerState(1)]

    def timels_worker(self):
        while True:
            try:
                op = self.opqueue.get()
                target_fn, args = op

                target_fn(*args)

                self.opqueue.task_done()

            except Exception as e:
                prints.fatal(e)

    def timer_watchdog(self):
        """Watchdog thread that monitors timers and triggers interrupts.

        This thread wakes up periodically or when signaled to check if any
        timer has expired. When a timer expires:
        1. STATUS.WRAPPED is set
        2. If RELOAD is set, VALUE is reloaded from RELOADVAL
        3. If IER is enabled, the corresponding IRQ is pended
        """
        while not self.watchdog_stop.is_set():
            self.watchdog_check.wait(timeout=0.001)
            self.watchdog_check.clear()

            with self.timer_lock:
                for timer in self.timers:
                    if not timer.running:
                        continue

                    current_value = self._compute_value_internal(timer)

                    if current_value == 0:
                        timer.status |= 1
                        timer.isr |= 1

                        # Handle reload
                        if (timer.control & 0x2) and (
                            timer.control & 0x4
                        ):
                            timer.start_value = timer.reloadval
                            timer.start_time_ns = time.perf_counter_ns()
                        else:
                            # Timer stops
                            timer.running = False

                        if timer.ier:
                            pend_external_irq(timer.irq)

    def start_worker(self):
        if not self.opthread:
            self.opthread = threading.Thread(target=self.timels_worker)
            self.opthread.daemon = True
            self.opthread.start()

        if not self.watchdog_thread:
            self.watchdog_stop.clear()
            self.watchdog_thread = threading.Thread(target=self.timer_watchdog)
            self.watchdog_thread.daemon = True
            self.watchdog_thread.start()

    def queue_read_worker_op(self, size: int, target_fn) -> int:
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()

    def queue_write_worker_op(self, size: int, value: int, target_fn) -> None:
        self.opqueue.put([target_fn, (size, value)])

    def _compute_value_internal(self, timer: TimerState) -> int:
        if not timer.running:
            return timer.start_value

        elapsed_ns = time.perf_counter_ns() - timer.start_time_ns
        elapsed_ticks = int(elapsed_ns / NS_PER_TICK)

        if elapsed_ticks >= timer.start_value:
            return 0

        return timer.start_value - elapsed_ticks

    def read_timer_control(self, size: int, queue: queue.Queue, index: int) -> None:
        with self.timer_lock:
            queue.put(self.timers[index].control)

    def write_timer_control(self, size: int, value: int, index: int) -> None:
        with self.timer_lock:
            timer = self.timers[index]
            old_control = timer.control
            timer.control = value

            was_enabled = old_control & 0x1
            is_enabled = value & 0x1

            if is_enabled and not was_enabled:
                if timer.start_value == 0:
                    timer.start_value = timer.load
                timer.start_time_ns = time.perf_counter_ns()
                timer.running = True
                self.watchdog_check.set()
            elif was_enabled and not is_enabled:
                current_value = self._compute_value_internal(timer)
                timer.start_value = current_value
                timer.running = False

    def read_timer_status(self, size: int, queue: queue.Queue, index: int) -> None:
        with self.timer_lock:
            queue.put(self.timers[index].status)

    def write_timer_status(self, size: int, value: int, index: int) -> None:
        # Writing to STATUS typically clears bits that are written as 1
        with self.timer_lock:
            self.timers[index].status &= ~value

    # =========================================================================
    # LOAD Register
    # =========================================================================

    def read_timer_load(self, size: int, queue: queue.Queue, index: int) -> None:
        with self.timer_lock:
            queue.put(self.timers[index].load)

    def write_timer_load(self, size: int, value: int, index: int) -> None:
        with self.timer_lock:
            timer = self.timers[index]
            timer.load = value

            # Writing to LOAD also sets VALUE and restarts the countdown
            timer.start_value = value
            if timer.running:
                timer.start_time_ns = time.perf_counter_ns()

            # Signal watchdog in case timer is about to expire
            self.watchdog_check.set()

    def read_timer_reloadval(self, size: int, queue: queue.Queue, index: int) -> None:
        with self.timer_lock:
            queue.put(self.timers[index].reloadval)

    def write_timer_reloadval(self, size: int, value: int, index: int) -> None:
        with self.timer_lock:
            self.timers[index].reloadval = value

    def read_timer_value(self, size: int, queue: queue.Queue, index: int) -> None:
        with self.timer_lock:
            timer = self.timers[index]
            current_value = self._compute_value_internal(timer)
            queue.put(current_value)

    def write_timer_value(self, size: int, value: int, index: int) -> None:
        with self.timer_lock:
            timer = self.timers[index]
            timer.start_value = value
            if timer.running:
                timer.start_time_ns = time.perf_counter_ns()

    def read_timer_step(self, size: int, queue: queue.Queue, index: int) -> None:
        with self.timer_lock:
            queue.put(self.timers[index].step)

    def write_timer_step(self, size: int, value: int, index: int) -> None:
        with self.timer_lock:
            self.timers[index].step = value

    def read_timer_ier(self, size: int, queue: queue.Queue, index: int) -> None:
        with self.timer_lock:
            queue.put(self.timers[index].ier)

    def write_timer_ier(self, size: int, value: int, index: int) -> None:
        with self.timer_lock:
            self.timers[index].ier = value

    def read_timer_isr(self, size: int, queue: queue.Queue, index: int) -> None:
        with self.timer_lock:
            queue.put(self.timers[index].isr)

    def write_timer_isr(self, size: int, value: int, index: int) -> None:
        with self.timer_lock:
            self.timers[index].isr &= ~value

    def read_timer_ipr(self, size: int, queue: queue.Queue, index: int) -> None:
        with self.timer_lock:
            queue.put(self.timers[index].ipr)

    def write_timer_ipr(self, size: int, value: int, index: int) -> None:
        with self.timer_lock:
            self.timers[index].ipr = value

    def read_timer_iar(self, size: int, queue: queue.Queue, index: int) -> None:
        with self.timer_lock:
            queue.put(self.timers[index].iar)

    def write_timer_iar(self, size: int, value: int, index: int) -> None:
        with self.timer_lock:
            timer = self.timers[index]
            if value & 1:
                timer.isr &= ~1
                timer.ipr &= ~1

    def read_timer_wakeup_ack(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        with self.timer_lock:
            queue.put(self.timers[index].wakeup_ack)

    def write_timer_wakeup_ack(
        self, size: int, value: int, index: int
    ) -> None:
        with self.timer_lock:
            self.timers[index].wakeup_ack = value

c_emu = LowSpeedTimer()
c_emu.start_worker()

# Within a TIMELS component, there are 2 timers that do the same thing.
# TIMER0 and TIMER1.
_SUB_TIMER_FUNC_MAP = {
    TIMELS_REGS["TIMER"]["CONTROL"]: [
        c_emu.read_timer_control, c_emu.write_timer_control
    ],
    TIMELS_REGS["TIMER"]["STATUS"]: [
        c_emu.read_timer_status, c_emu.write_timer_status
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
    TIMELS_REGS["TIMER"]["STEP"]: [
        c_emu.read_timer_step, c_emu.write_timer_step
    ],
    TIMELS_REGS["TIMER"]["IER"]: [
        c_emu.read_timer_ier, c_emu.write_timer_ier
    ],
    TIMELS_REGS["TIMER"]["ISR"]: [
        c_emu.read_timer_isr, c_emu.write_timer_isr
    ],
    TIMELS_REGS["TIMER"]["IPR"]: [
        c_emu.read_timer_ipr, c_emu.write_timer_ipr
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


def component_stop_timer_debug() -> None:
    with c_emu.timer_lock:
        for timer in c_emu.timers:
            if timer.running:
                current_value = c_emu._compute_value_internal(timer)
                timer.start_value = current_value
                timer.running = False

    c_emu.watchdog_check.set()


def component_start_timer_debug() -> None:
    with c_emu.timer_lock:
        for timer in c_emu.timers:
            if timer.start_value == 0 and timer.load:
                timer.start_value = timer.load

            if not timer.running and timer.start_value != 0:
                timer.start_time_ns = time.perf_counter_ns()
                timer.running = True

    c_emu.watchdog_check.set()