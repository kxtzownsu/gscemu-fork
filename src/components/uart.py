# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import unicorn as qemu
import queue
import threading
import sys

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from src.emulators.haven.registers import REG_DEFS, UART_REGS
from lib.helpers import unhandled_register_exit, unhandled_register_io, BIT

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

_REG_BASE_ADDR = REG_DEFS["UART0"]["base_addr"]

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
                op = self.opqueue.get()
                target_fn, args = op

                # update STATE based on input queue
                if self.input_queue.empty():
                    self.state |= BIT(7) # True
                else:
                    self.state &= ~BIT(7) # False

                target_fn(*args) # Splat the arguments into the target_fn

                # For write operations, this doesn't do anything. For read
                # operations, we need to tell the handler that we have written
                # the value into the address, and execution can proceed.
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

    def queue_read_worker_op(self, target_fn, addr: int):
        self.opqueue.put([target_fn, (addr,)])
        self.opqueue.join()
        
    def queue_write_worker_op(self, target_fn, val: int):
        self.opqueue.put([target_fn, (val,)])

    def read_wdata(self, addr, *args, **kwargs) -> None:
        unhandled_register_io(prints, "READ", "UART0", "WDATA")
        ucmutex().int32_mem_write(addr, 0)

    def write_wdata(self, val: int, *args, **kwargs) -> None:
        if not (self.state & BIT(0)):
            try:
                sys.stdout.write(chr(val))
                sys.stdout.flush()
            except:
                pass
        else:
            prints.warning("WDATA written to whilst STATE TX busy set!")

    def read_nco(self, addr: int, *args, **kwargs) -> None:
        ucmutex().int32_mem_write(addr, self.nco)

    def write_nco(self, val: int, *args, **kwargs) -> None:
        self.nco = val

    def read_ctrl(self, addr: int, *args, **kwargs) -> None:
        ucmutex().int32_mem_write(addr, self.ctrl)

    def write_ctrl(self, val: int, *args, **kwargs) -> None:
        self.ctrl = val

    def read_state(self, addr: int, *args, **kwargs) -> None:
        ucmutex().int32_mem_write(addr, self.state)

    def write_state(self, val: int, *args, **kwargs) -> None:
        self.state = val

    def read_rdata(self, addr: int, *args, **kwargs) -> None:
        try:
            char = self.input_queue.get_nowait()
        except queue.Empty:
            prints.warning("RDATA read when no available chars!")
            char = 0

        ucmutex().int32_mem_write(addr, char)

    def write_rdata(self, val: int, *args, **kwargs) -> None:
        unhandled_register_io(prints, "WRITE", "UART0", "RDATA")

c_emu = UartController()
c_emu.start_worker()

_REG_FUNC_MAP = {
    UART_REGS["WDATA"]: [c_emu.read_wdata, c_emu.write_wdata],
    UART_REGS["NCO"]: [c_emu.read_nco, c_emu.write_nco],
    UART_REGS["CTRL"]: [c_emu.read_ctrl, c_emu.write_ctrl],
    UART_REGS["STATE"]: [c_emu.read_state, c_emu.write_state],
    UART_REGS["RDATA"]: [c_emu.read_rdata, c_emu.read_rdata],
}

def component_handler(
    instance: int,
    uc: qemu.Uc,
    access,
    address: int,
    size: int,
    value: int,
    user_data
) -> bool:
    """Main component handler for UART"""
    
    # UART 1 and 2 is actually redundant, but we need it for compatibility
    # with guest code that expects these peripherals to exist. It is pointless
    # to support UART 1 and 2, it's not connected to anything.
    if instance in [1, 2]:
        prints.warning("We do not manage UART1-2, it is AP/EC related.")

    # If we do intend to support UART1 and 2, this code needs to be refactored
    # for such a purpose. The code only supports UART0 reads/writes for now.
    reg_offset = address - _REG_BASE_ADDR

    try:
        if access == qemu.UC_MEM_READ:
            c_emu.queue_read_worker_op(_REG_FUNC_MAP[reg_offset][0], address)
        elif access == qemu.UC_MEM_WRITE:
            c_emu.queue_write_worker_op(_REG_FUNC_MAP[reg_offset][1], value)

    except KeyError:
        unhandled_register_exit(prints, "UART0", address)

def component0_handler(
    uc: qemu.Uc,
    access,
    address: int,
    size: int,
    value: int,
    user_data
) -> bool:
    """Instance handler for UART0"""

    return component_handler(0, uc, access, address, size, value, user_data)

def component1_handler(
    uc: qemu.Uc,
    access,
    address: int,
    size: int,
    value: int,
    user_data
) -> bool:
    """Instance handler for UART1"""

    return component_handler(1, uc, access, address, size, value, user_data)

def component2_handler(
    uc: qemu.Uc,
    access,
    address: int,
    size: int,
    value: int,
    user_data
) -> bool:
    """Instance handler for UART2"""

    return component_handler(2, uc, access, address, size, value, user_data)