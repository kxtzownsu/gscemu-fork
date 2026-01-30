# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer
"""CRYTPO bignum accelerator implementation."""

import unicorn as qemu
import queue
import threading
import typing
import time

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from src.emulators.haven.registers import CRYPTO_REGS
from lib.helpers import (
    unhandled_register_exit, 
    unhandled_register_io,
    idx_regs_to_regmap
)
from src.components.m3 import pend_external_irq

# ot_dsim package imports.
from ot_dsim.bignum_lib.machine import Machine as CryptoEmu

from ot_dsim.bignum_lib.instructions import InstructionFactory as CryptoEmuIF
from ot_dsim.bignum_lib.instructions import InsContext as CryptoEmuICtx

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

class CryptoAccelerator:
    def __init__(self):
        self.opthread = None
        self.opqueue = queue.Queue()

        self.crypto_emulator = None
        self.control = 0
        self.rand_stall_ctl = 0
        self.host_cmd = 0

    def crypto_worker(self):
        while True:
            try:
                op = self.opqueue.get()
                target_fn, args = op

                target_fn(*args)

                self.opqueue.task_done()

                if self.control:
                    self.control_process()

                if self.host_cmd:
                    time.sleep(0.01)
                    pend_external_irq(4)
                    self.host_cmd = 0

            except Exception as e:
                prints.fatal(e)

    def start_worker(self):
        if not self.opthread:
            self.opthread = threading.Thread(target=self.crypto_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn):
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()
    
    def queue_write_worker_op(self, size: int, value: int, target_fn):
        self.opqueue.put([target_fn, (size, value)])

    def control_process(self):
        if self.control & 1: # RESET
            self.clear_emulator_object()

        elif self.control & 2: # BREAK
            # Undefined behavior, just pass
            pass

        elif self.control & 4: # RESUME
            # Undefined behavior, just pass
            pass
        
        # At this point, the writes should have been processed.
        self.control = 0

    def clear_emulator_object(self):
        self.crypto_emulator = None

    def read_control(self, size: int, queue: queue.Queue):
        # Should be zero everytime this is read anyways.
        queue.put(self.control)
    
    def write_control(self, size: int, value: int):
        val = value & 7

        # Check if more than 1 bit set.
        if (val & (val-1)):
            # More than 1 bit set, ignore the write and return.
            return
        
        self.control = val

    def read_wipe_secrets(self, size: int, queue: queue.Queue):
        unhandled_register_io(prints, "READ", "CRYPTO", "WIPE_SECRETS")
        queue.put(0)
    
    def write_wipe_secrets(self, size: int, value: int):
        if value:
            self.clear_emulator_object()
    
    def read_imem(self, size: int, queue: queue.Queue, index: int):
        queue.put(0)

    def write_imem(self, size: int, value: int, index: int):
        return
    
    def read_dmem(self, size: int, queue: queue.Queue, index: int):
        queue.put(0)

    def write_dmem(self, size: int, value: int, index: int):
        return
    
    def read_int_state(self, size: int, queue: queue.Queue):
        queue.put(0)
    
    def write_int_state(self, size: int, value: int):
        return
    
    def read_int_enable(self, size: int, queue: queue.Queue):
        queue.put(0)
    
    def write_int_enable(self, size: int, value: int):
        return
    
    def read_rand_stall_ctl(self, size: int, queue: queue.Queue):
        queue.put(self.rand_stall_ctl)
    
    def write_rand_stall_ctl(self, size: int, value: int):
        self.rand_stall_ctl = value

    def read_host_cmd(self, size: int, queue: queue.Queue):
        queue.put(self.host_cmd)
    
    def write_host_cmd(self, size: int, value: int):
        self.host_cmd = value

c_emu = CryptoAccelerator()
c_emu.start_worker()

_REG_FUNC_MAP = {
    CRYPTO_REGS["CONTROL"]: [c_emu.read_control, c_emu.write_control],
    CRYPTO_REGS["WIPE_SECRETS"]: [
        c_emu.read_wipe_secrets, c_emu.write_wipe_secrets
    ],
    CRYPTO_REGS["INT_ENABLE"]: [
        c_emu.read_int_enable, c_emu.write_int_enable
    ],
    CRYPTO_REGS["INT_STATE"]: [
        c_emu.read_int_state, c_emu.write_int_state
    ],
    CRYPTO_REGS["RAND_STALL_CTL"]: [
        c_emu.read_rand_stall_ctl, c_emu.write_rand_stall_ctl
    ],
    CRYPTO_REGS["HOST_CMD"]: [
        c_emu.read_host_cmd, c_emu.write_host_cmd
    ]
}

idx_regs_to_regmap(
    _REG_FUNC_MAP, CRYPTO_REGS["IMEM_DUMMY"],
    c_emu.read_imem, c_emu.write_imem
)

idx_regs_to_regmap(
    _REG_FUNC_MAP, CRYPTO_REGS["DMEM_DUMMY"],
    c_emu.read_dmem, c_emu.write_dmem
)

def component_read_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    user_data: typing.Any,
) -> int:
    try:
        return c_emu.queue_read_worker_op(size, _REG_FUNC_MAP[offset][0])
    except KeyError:
        unhandled_register_exit(g_uc(), ucthread(), prints, "CRYPTO", offset)

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
        unhandled_register_exit(g_uc(), ucthread(), prints, "CRYPTO", offset)
