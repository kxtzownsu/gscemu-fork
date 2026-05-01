# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer
"""CRYTPO bignum accelerator implementation."""

import queue
import threading
import time
import traceback
import typing

import unicorn as qemu
from ot_dsim.bignum_lib.instructions import InsContext as CryptoEmuICtx
from ot_dsim.bignum_lib.instructions import InstructionFactory as CryptoEmuIF

# ot_dsim package imports.
from ot_dsim.bignum_lib.machine import Machine as CryptoEmu

from env import *
from lib.emulator_context import ComponentObjects, EmulatorContext
from lib.helpers import (
    idx_regs_to_regmap,
    unhandled_register_exit,
    unhandled_register_io,
)
from lib.logger import GscemuLogger

from .m3 import pend_external_irq, unpend_external_irq
from .timels import component_start_timer_debug, component_stop_timer_debug

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


class CryptoAccelerator:
    def __init__(self, ctx: EmulatorContext):
        self.ctx = ctx

        self.assembler = {"factory": CryptoEmuIF(), "ins_ctx": CryptoEmuICtx()}

        self.opthread = None
        self.opqueue = queue.Queue()

        self.crypto_emulator = None
        self.control = 0
        self.rand_stall_ctl = 0
        self.host_cmd = 0

        self.imem_mem = [0] * 1024
        self.imem_assembled = [0] * 1024

        self.dmem_mem = [0] * 128

    def crypto_worker(self):
        while True:
            try:
                op = self.opqueue.get()
                target_fn, args = op

                target_fn(*args)

                if self.control:
                    self.control_process()

                if self.host_cmd:
                    # start_time = time.perf_counter()
                    if GSCEMULATOR_DISABLE_CRYPTO_ENGINE:
                        time.sleep(0.01)
                        pend_external_irq(self.ctx.c_fast.m3, 4)
                        self.host_cmd = 0
                        continue

                    component_stop_timer_debug(self.ctx.c_fast.timels)
                    if self.crypto_emulator is None:
                        self.crypto_emulator = CryptoEmu(
                            self.dmem_mem.copy(),
                            self.imem_assembled.copy(),
                            self.host_cmd,
                            None,
                            CryptoEmuICtx(),
                        )
                    else:
                        self.crypto_emulator.set_pc(self.host_cmd, True)

                    self.host_cmd = 0  # Clear HOST_CMD

                    try:
                        while self.crypto_emulator.step_continue():
                            pass
                    except Exception:
                        traceback.print_exc()
                        if self.crypto_emulator is not None:
                            prints.debug(
                                self.crypto_emulator.get_instruction(
                                    self.crypto_emulator.get_pc()
                                )
                            )
                        prints.warning("CRYPTO engine died :(")

                    self.dmem_mem = self.crypto_emulator.get_full_dmem().copy()
                    component_start_timer_debug(self.ctx.c_fast.timels)

                    pend_external_irq(self.ctx.c_fast.m3, 4)
                    # print(time.perf_counter() - start_time)

                self.opqueue.task_done()

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
        if self.control & 1:  # RESET
            self.clear_emulator_object()

        elif self.control & 2:  # BREAK
            # Undefined behavior, just pass
            pass

        elif self.control & 4:  # RESUME
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
        if val & (val - 1):
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
        queue.put(self.imem_mem[index])

    def write_imem(self, size: int, value: int, index: int):
        # Clear emulator state on IMEM write if emulator state has been
        # created?
        if self.crypto_emulator is not None:
            self.crypto_emulator = None
            self.imem_mem = [0] * 1024
            self.imem_assembled = [0] * 1024

        try:
            assembled = self.assembler["factory"].factory_bin(
                value, self.assembler["ins_ctx"]
            )
        except Exception:
            if not (value == 0xDDDDDDDD):
                prints.warning(
                    f"IMEM instruction was invalid! noping out insn {value:x}!"
                )

            assembled = self.assembler["factory"].factory_bin(
                0xFC000000, self.assembler["ins_ctx"]
            )

        self.imem_mem[index] = value
        self.imem_assembled[index] = assembled

    def read_dmem(self, size: int, queue: queue.Queue, index: int):
        element_idx = index // 8
        word_idx = index % 8
        bit_offset = word_idx * 32

        if self.crypto_emulator is not None:
            queue.put(
                (self.crypto_emulator.get_dmem(element_idx) >> bit_offset)
                & 0xFFFFFFFF
            )
        else:
            queue.put((self.dmem_mem[element_idx] >> bit_offset) & 0xFFFFFFFF)

    def write_dmem(self, size: int, value: int, index: int):
        element_idx = index // 8
        word_idx = index % 8
        value = value & 0xFFFFFFFF
        bit_offset = word_idx * 32
        mask = ((1 << 256) - 1) ^ (0xFFFFFFFF << bit_offset)

        if self.crypto_emulator is not None:
            current_element = self.crypto_emulator.get_dmem(element_idx)
            self.crypto_emulator.set_dmem(
                element_idx, (current_element & mask) | (value << bit_offset)
            )
        else:
            current_element = self.dmem_mem[element_idx]
            self.dmem_mem[element_idx] = (current_element & mask) | (
                value << bit_offset
            )

    def read_int_state(self, size: int, queue: queue.Queue):
        # Doesn't matter
        queue.put(0)

    def write_int_state(self, size: int, value: int):
        if value & 0x2:
            unpend_external_irq(self.ctx.c_fast.m3, 4)

    def read_int_enable(self, size: int, queue: queue.Queue):
        # Doesn't matter
        queue.put(0)

    def write_int_enable(self, size: int, value: int):
        # Doesn't matter
        return

    def read_rand_stall_ctl(self, size: int, queue: queue.Queue):
        # Doesn't matter
        queue.put(self.rand_stall_ctl)

    def write_rand_stall_ctl(self, size: int, value: int):
        # Doesn't matter
        self.rand_stall_ctl = value

    def read_host_cmd(self, size: int, queue: queue.Queue):
        queue.put(self.host_cmd)

    def write_host_cmd(self, size: int, value: int):
        self.host_cmd = value - 0x08000000


def init_CryptoAccelerator(ctx: EmulatorContext, regs: dict):
    c_emu = CryptoAccelerator(ctx)
    c_emu.start_worker()

    reg_fn_map = {
        regs["CONTROL"]: [c_emu.read_control, c_emu.write_control],
        regs["WIPE_SECRETS"]: [
            c_emu.read_wipe_secrets,
            c_emu.write_wipe_secrets,
        ],
        regs["INT_ENABLE"]: [c_emu.read_int_enable, c_emu.write_int_enable],
        regs["INT_STATE"]: [c_emu.read_int_state, c_emu.write_int_state],
        regs["RAND_STALL_CTL"]: [
            c_emu.read_rand_stall_ctl,
            c_emu.write_rand_stall_ctl,
        ],
        regs["HOST_CMD"]: [c_emu.read_host_cmd, c_emu.write_host_cmd],
    }

    idx_regs_to_regmap(
        reg_fn_map, regs["IMEM_DUMMY"], c_emu.read_imem, c_emu.write_imem
    )

    idx_regs_to_regmap(
        reg_fn_map, regs["DMEM_DUMMY"], c_emu.read_dmem, c_emu.write_dmem
    )

    def component_read_handler(
        uc_unused: qemu.Uc,
        offset: int,
        size: int,
        user_data: typing.Any,
    ) -> int:
        try:
            return c_emu.queue_read_worker_op(size, reg_fn_map[offset][0])
        except KeyError:
            unhandled_register_exit(ctx, prints, "CRYPTO", offset)

    def component_write_handler(
        uc_unused: qemu.Uc,
        offset: int,
        size: int,
        value: int,
        user_data: typing.Any,
    ) -> None:
        try:
            c_emu.queue_write_worker_op(size, value, reg_fn_map[offset][1])
        except KeyError:
            unhandled_register_exit(ctx, prints, "CRYPTO", offset)

    return ComponentObjects(
        c_emu, component_read_handler, component_write_handler
    )
