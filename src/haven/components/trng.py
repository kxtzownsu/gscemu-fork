# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer
"""Cr50 TRNG engine

On real silicon, the other registers matter. To not overcomplicate things, let's
just stick to the built-in secrets module for now.
"""

import typing
import unicorn as qemu
import queue
import threading
import secrets

from lib.emulator_context import EmulatorContext, ComponentObjects
from env import *
from lib.logger import GscemuLogger
from lib.helpers import (
    unhandled_register_exit, 
    unhandled_register_io
)

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

class TRNGEngine:
    def __init__(self, ctx: EmulatorContext):
        self.ctx = ctx
        
        self.opthread = None
        self.opqueue = queue.Queue()

        self.ldo_ctrl = 0
        self.analog_ctrl = 0
        self.post_processing_ctrl = 0
        self.secure_post_processing_ctrl = 0

        # Allowed range of values that can be generated
        self.allowed_values = 0

        # How many bits should we take from the sample to populate the 32bit
        # value?
        self.slice_max_upper_limit = 0
        self.slice_min_lower_limit = 0

        self.go_event = 0
        self.stop_work = 0

        self.read_data = 0
        self.empty = 0

        self.timeout_counter = 0
        self.timeout_max_try_num = 0

        self.fsm_state = 0
        self.output_time_counter = 0

        # 1 = on, 0 = off
        self.power_down_b = 0

    def trng_worker(self):
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
            self.opthread = threading.Thread(target=self.trng_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn):
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()
        
    def queue_write_worker_op(self, size: int, value: int, target_fn):
        self.opqueue.put([target_fn, (size, value)])

    def read_read_data(self, size: int, queue: queue.Queue):
        queue.put(secrets.randbits(32))
    
    def write_read_data(self, size: int, value: int):
        unhandled_register_io(prints, "WRITE", "TRNG", "READ_DATA")
        return

    def read_secure_post_processing_ctrl(self, size: int, queue: queue.Queue):
        queue.put(self.secure_post_processing_ctrl)

    def write_secure_post_processing_ctrl(self, size: int, value: int):
        self.secure_post_processing_ctrl = value

    def read_post_processing_ctrl(self, size: int, queue: queue.Queue):
        queue.put(self.post_processing_ctrl)

    def write_post_processing_ctrl(self, size: int, value: int):
        self.post_processing_ctrl = value

    def read_ldo_ctrl(self, size: int, queue: queue.Queue):
        queue.put(self.ldo_ctrl)

    def write_ldo_ctrl(self, size: int, value: int):
        self.ldo_ctrl = value

    def read_analog_ctrl(self, size: int, queue: queue.Queue):
        queue.put(self.analog_ctrl)

    def write_analog_ctrl(self, size: int, value: int):
        self.analog_ctrl = value

    def read_allowed_values(self, size: int, queue: queue.Queue):
        queue.put(self.allowed_values)

    def write_allowed_values(self, size: int, value: int):
        self.allowed_values = value

    def read_slice_max_upper_limit(self, size: int, queue: queue.Queue):
        queue.put(self.slice_max_upper_limit)

    def write_slice_max_upper_limit(self, size: int, value: int):
        self.slice_max_upper_limit = value

    def read_slice_min_lower_limit(self, size: int, queue: queue.Queue):
        queue.put(self.slice_min_lower_limit)

    def write_slice_min_lower_limit(self, size: int, value: int):
        self.slice_min_lower_limit = value

    def read_power_down_b(self, size: int, queue: queue.Queue):
        queue.put(self.power_down_b)

    def write_power_down_b(self, size: int, value: int):
        self.power_down_b = value

    def read_go_event(self, size: int, queue: queue.Queue):
        queue.put(self.go_event)

    def write_go_event(self, size: int, value: int):
        self.go_event = value

    def read_stop_work(self, size: int, queue: queue.Queue):
        queue.put(self.stop_work)

    def write_stop_work(self, size: int, value: int):
        self.stop_work = value

    def read_empty(self, size: int, queue: queue.Queue):
        queue.put(self.empty)

    def write_empty(self, size: int, value: int):
        self.empty = value

    def read_timeout_counter(self, size: int, queue: queue.Queue):
        queue.put(self.timeout_counter)

    def write_timeout_counter(self, size: int, value: int):
        self.timeout_counter = value

    def read_timeout_max_try_num(self, size: int, queue: queue.Queue):
        queue.put(self.timeout_max_try_num)

    def write_timeout_max_try_num(self, size: int, value: int):
        self.timeout_max_try_num = value

    def read_fsm_state(self, size: int, queue: queue.Queue):
        queue.put(self.fsm_state)

    def write_fsm_state(self, size: int, value: int):
        self.fsm_state = value

    def read_output_time_counter(self, size: int, queue: queue.Queue):
        queue.put(self.output_time_counter)

    def write_output_time_counter(self, size: int, value: int):
        self.output_time_counter = value

def init_TRNGEngine(ctx: EmulatorContext, regs: dict):
    c_emu = TRNGEngine(ctx)
    c_emu.start_worker()

    reg_fn_map = {
        regs["READ_DATA"]: [c_emu.read_read_data, c_emu.write_read_data],
        regs["SECURE_POST_PROCESSING_CTRL"]: [
            c_emu.read_secure_post_processing_ctrl, 
            c_emu.write_secure_post_processing_ctrl
        ],
        regs["POST_PROCESSING_CTRL"]: [
            c_emu.read_post_processing_ctrl, 
            c_emu.write_post_processing_ctrl
        ],
        regs["LDO_CTRL"]: [
            c_emu.read_ldo_ctrl, 
            c_emu.write_ldo_ctrl
        ],
        regs["ANALOG_CTRL"]: [
            c_emu.read_analog_ctrl, 
            c_emu.write_analog_ctrl
        ],
        regs["ALLOWED_VALUES"]: [
            c_emu.read_allowed_values, 
            c_emu.write_allowed_values
        ],
        regs["SLICE_MAX_UPPER_LIMIT"]: [
            c_emu.read_slice_max_upper_limit, 
            c_emu.write_slice_max_upper_limit
        ],
        regs["SLICE_MIN_LOWER_LIMIT"]: [
            c_emu.read_slice_min_lower_limit, 
            c_emu.write_slice_min_lower_limit
        ],
        regs["POWER_DOWN_B"]: [
            c_emu.read_power_down_b, 
            c_emu.write_power_down_b
        ],
        regs["GO_EVENT"]: [c_emu.read_go_event, c_emu.write_go_event],
        regs["STOP_WORK"]: [c_emu.read_stop_work, c_emu.write_stop_work],
        regs["EMPTY"]: [c_emu.read_empty, c_emu.write_empty],
        regs["TIMEOUT_COUNTER"]: [
            c_emu.read_timeout_counter, 
            c_emu.write_timeout_counter
        ],
        regs["TIMEOUT_MAX_TRY_NUM"]: [
            c_emu.read_timeout_max_try_num, 
            c_emu.write_timeout_max_try_num
        ],
        regs["FSM_STATE"]: [c_emu.read_fsm_state, c_emu.write_fsm_state],
        regs["OUTPUT_TIME_COUNTER"]: [
            c_emu.read_output_time_counter, 
            c_emu.write_output_time_counter
        ],
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
            unhandled_register_exit(ctx, prints, "TRNG0", offset)

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
            unhandled_register_exit(ctx, prints, "TRNG0", offset)

    return ComponentObjects(
        c_emu, component_read_handler, component_write_handler
    )