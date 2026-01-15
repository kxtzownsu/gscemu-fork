# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import typing
import unicorn as qemu
import queue
import threading
import struct
import hashlib
import hmac

from lib.globalvars import *
from env import *
from lib.threadutils import FifoLock
from lib.logger import GscemuLogger
from src.emulators.haven.registers import REG_DEFS, KEYMGR_REGS
from lib.helpers import (
    unhandled_register_io, 
    unhandled_register_exit,
    idx_regs_to_regmap,
    idx_retqueue_regs_to_regmap
)

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

class ShaEngine:
    def __init__(self):
        self.opqueue = queue.Queue()
        self.opthread = None

        self.recieve_data = False # Used for LIVESTREAM mode
        self.start_hash = False

        self.itop = 0
        self.trig = 0

        self.msglen_lo = 0
        self.msglen_hi = 0
        self.msglen_full = 0 # Combination of LO + HI.
        self.en = 0
        self.wr_en = 0

        self.input_fifo = bytearray()
        self.sts_h = [0] * 8
        self.key_w = [0] * 8

        self.use_cert = {
            "INDEX": 0,
            "ENABLE": 0,
            "CHECK_ONLY": 0,
        }
        self.rand_stall_ctl = {
            "STALL_EN": 0,
            "FREQ": 0,
        }
        self.cert_override_ptr = {
            "DIGEST": 0,
            "KEY": 0,
        }

    def sha_worker(self):
        while True:
            try:
                # Wait for the next operation to enter the queue
                op = self.opqueue.get()
                target_fn, args = op
                
                target_fn(*args) # Splat our arguments into the target_fn

                # For write operations, this doesn't do anything. For read
                # operations, we need to tell the handler that we have written
                # the value into the address, and execution can proceed.
                self.opqueue.task_done()

                # Now, the SHA engine needs to check if we need to proceed with
                # any operations.

                # Check if TRIG has a value. If so, we need to process that 
                # operation.
                if self.trig:
                    self.trig_process()

                # If LIVESTREAM is not enabled, then check if oneshot has
                # started processing data. If so, then we check if the buffer
                # has reached the msglen.
                if not (self.en & 16): # BIT(4)
                    if self.recieve_data:
                        self.oneshot_check()

                # Check if we should start hashing data now.
                if self.start_hash:
                    self.hash_data()

            except Exception as e:
                prints.fatal(e)

    def start_worker(self):
        if not self.opthread:
            self.opthread = threading.Thread(target=self.sha_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def trig_process(self):
        match self.trig:
            case 1: # BIT(0)
                # If this is a USE_CERT operation, just ignore it and say
                # the op is done.
                if self.use_cert["ENABLE"]:
                    self.use_cert["ENABLE"] = 0
                    self.itop = 1
                else:
                    # Not a USE_CERT operation.
                    # Enable recieving data for LIVESTREAM or oneshot.
                    self.recieve_data = True

                self.trig &= ~1 # Clear the TRIG bit

            case 2: # BIT(1)
                # Wipe all the values in the SHA engine.
                self.recieve_data = False
                self.itop = 0
                self.msglen_lo = 0
                self.msglen_hi = 0
                self.en = 0
                self.wr_en = 0
                self.input_fifo = bytearray()
                self.sts_h = [0] * 8
                self.key_w = [0] * 8

                self.trig &= ~2 # Clear the TRIG bit

            case 4: # BIT(2)
                # Undocumented and unused TRIG value.
                self.trig &= ~4 # Clear the TRIG bit

            case 8: # BIT(3)
                # This means the firmware has finished streaming the data to
                # hash. We should kick off the SHA engine. This is only
                # applicable in LIVESTREAM mode.

                if self.en & 16: # BIT(4)
                    self.recieve_data = False
                    self.start_hash = True
                
                self.trig &= ~8 # Clear the TRIG bit
            
            case _:
                prints.fatal("SHA_TRIG received an invalid value")

    def oneshot_check(self):
        if len(self.input_fifo) == self.msglen_full:
            prints.debug("SHA INPUT_FIFO fully populated in oneshot mode!")
            self.recieve_data = False
            self.start_hash = True

    def hash_data(self):
        prints.debug("SHA engine hashing kicked off!")
        prints.debug(f"SHA engine running with self.en=0x{self.en:x}")
        engine = None
        engine_settings = self.en & (2 | 32) # BIT(1) | BIT(5)

        match engine_settings:
            case 0: # SHA256
                engine = hashlib.sha256(self.input_fifo)
            case 2: # SHA1
                engine = hashlib.sha1(self.input_fifo)
            case 32: # SHA256 + HMAC
                derived_hmac_key = bytearray()
                for i in self.key_w:
                    derived_hmac_key.extend(struct.pack("<I", i))

                engine = hmac.new(
                    derived_hmac_key,
                    self.input_fifo, 
                    hashlib.sha256
                )
            case _:
                prints.fatal("unsupported ShaEngine CFG_EN state")
            
        digest = engine.digest()
        for i in range(8):
            self.sts_h[i] = int.from_bytes(digest[i*4:(i+1)*4], 'little')

        if self.en & 65536: # BIT(16)
            self.itop = 1

        self.start_hash = False
        self.input_fifo = bytearray()

    def queue_read_worker_op(self, target_fn, size: int):
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()
        
    def queue_write_worker_op(self, target_fn, size: int, value: int):
        self.opqueue.put([target_fn, (size, value)])

    def read_cfg_msglen_lo(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.msglen_lo)

    def write_cfg_msglen_lo(self, size: int, value: int) -> None:
        if self.recieve_data:
            return
        
        self.msglen_lo = value
        self.msglen_full = (self.msglen_hi << 32) | self.msglen_lo

    def read_cfg_msglen_hi(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.msglen_hi)

    def write_cfg_msglen_hi(self, size: int, value: int) -> None:
        if self.recieve_data:
            return
        
        self.msglen_hi = value
        self.msglen_full = (self.msglen_hi << 32) | self.msglen_lo

    def read_cfg_en(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.en)

    def write_cfg_en(self, size: int, value: int) -> None:
        if self.recieve_data:
            return
        
        self.en = value

    def read_cfg_wr_en(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.wr_en)

    def write_cfg_wr_en(self, size: int, value: int) -> None:
        self.wr_en = value

    def read_trig(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.trig)

    def write_trig(self, size: int, value: int) -> None:
        self.trig = value

    def read_itop(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.itop)

    def write_itop(self, size: int, value: int) -> None:
        self.itop = value

    def read_input_fifo(self, size: int, queue: queue.Queue) -> None:
        unhandled_register_io(prints, "READ", "KEYMGR0", "INPUT_FIFO")
        queue.put(0)

    def write_input_fifo(self, size: int, value: int) -> None:
        if not self.recieve_data:
            return
        
        match size:
            case 1:
                self.input_fifo.append(value & 0xFF)
            case 4:
                self.input_fifo.extend(struct.pack("<I", value))
            case _:
                prints.warning(f"Unexpected write size={size}, ignoring val.")

    def read_sts_h(self, size: int, queue: queue.Queue, index: int) -> None:
        queue.put(self.sts_h[index])

    def write_sts_h(self, size: int, value: int, index: int) -> None:
        unhandled_register_io(prints, "WRITE", "KEYMGR0", f"STS_H_{index}")

    def read_key_w(self, size: int, queue: queue.Queue, index: int) -> None:
        queue.put(self.key_w[index])

    def write_key_w(self, size: int, value: int, index: int) -> None:
        self.key_w[index] = value

    def read_rand_stall_ctl(self, size: int, queue: queue.Queue) -> None:
        val = (
            self.rand_stall_ctl["STALL_EN"] |
            (self.rand_stall_ctl["FREQ"] << 1)
        )
        queue.put(val)

    def write_rand_stall_ctl(self, size: int, value: int) -> None:
        stall_en = (value & 0x1)
        stall_freq = (value & 0x6) >> 0x1

        if stall_en:
            # If STALL_EN, that means random nops enabled. Only accept
            # writes to STALL_EN
            self.rand_stall_ctl["STALL_EN"] = stall_en
        else:
            # STALL_EN not enabled, therefore allow writes to STALL_EN and FREQ
            self.rand_stall_ctl["STALL_EN"] = stall_en
            self.rand_stall_ctl["FREQ"] = stall_freq

    def read_cert_override(self, size: int, queue: queue.Queue) -> None:
        val = (
            self.cert_override_ptr["DIGEST"] |
            self.cert_override_ptr["KEY"] << 0x10
        )
        queue.put(val)

    def write_cert_override(self, size: int, value: int) -> None:    
        self.cert_override_ptr["DIGEST"] = (value & 0x3f)
        self.cert_override_ptr["KEY"] = (value & 0x3f0000) >> 0x10

    def read_use_cert(self, size: int, queue: queue.Queue) -> None:
        val = (
            self.use_cert["INDEX"] |
            self.use_cert["ENABLE"] << 0x6 |
            self.use_cert["CHECK_ONLY"] << 0x7
        )
        queue.put(val)

    def write_use_cert(self, size: int, value: int) -> None:        
        self.use_cert["INDEX"] = (value & 0x3f)
        self.use_cert["ENABLE"] = (value & 0x40) >> 0x6
        self.use_cert["CHECK_ONLY"] = (value & 0x80) >> 0x7
        
class KeymgrController:
    def __init__(self):
        self.mutex = FifoLock() # Only use this for KeyManager specific ops.
        self.shaengine = ShaEngine()
        self.aesengine = None

        self.cert_revoke_ctrl = [
            0xa8028a82, 0xaaaaaaaa, 0xaaaa
        ]

        self.hkey_rwr = [0] * 8
        self.hkey_err_flags = 0

        self.rwr_vld = 0
        self.rwr_lock = 0

        self.shaengine.start_worker()

    def read_hkey_rwr(self, size: int, index: int) -> None:
        with self.mutex:
            return self.hkey_rwr[index]

    def write_hkey_rwr(
        self, size: int, value: int, index: int
    ) -> None:
        with self.mutex:
            self.hkey_rwr[index] = value

    def read_hkey_err_flags(self, size: int) -> None:
        with self.mutex:
            return self.hkey_err_flags

    def write_hkey_err_flags(self, size: int, value: int) -> None:
        with self.mutex:
            self.hkey_err_flags = value

    def read_rwr_vld(self, size: int) -> None:
        with self.mutex:
            return self.rwr_vld

    def write_rwr_vld(self, size: int, value: int) -> None:
        with self.mutex:
            self.rwr_vld = value

    def read_rwr_lock(self, size: int) -> None:
        with self.mutex:
            return self.rwr_lock

    def write_rwr_lock(self, size: int, value: int) -> None:
        with self.mutex:
            self.rwr_lock = value

    def read_cert_revoke_ctrl(
        self, size: int, index: int
    ) -> None:
        with self.mutex:
            return self.cert_revoke_ctrl[index]

    def write_cert_revoke_ctrl(
        self, size: int, value: int, index: int
    ) -> None:
        # with self.mutex:

        # We should be able to write to this register, but we do not implement
        # that for now.
        pass

c_emu = KeymgrController()

_REG_FUNC_MAP = {
    KEYMGR_REGS["RWR_VLD"]: [
        c_emu.read_rwr_vld,
        c_emu.write_rwr_vld,
    ],
    KEYMGR_REGS["RWR_LOCK"]: [
        c_emu.read_rwr_lock,
        c_emu.write_rwr_lock,
    ],
    KEYMGR_REGS["HKEY_ERR_FLAGS"]: [
        c_emu.read_hkey_err_flags,
        c_emu.write_hkey_err_flags,
    ],
}

_SHAENGINE_FUNC_MAP = {
    KEYMGR_REGS["SHA"]["CFG"]["MSGLEN_LO"]: [
        c_emu.shaengine.read_cfg_msglen_lo,
        c_emu.shaengine.write_cfg_msglen_lo,
    ],
    KEYMGR_REGS["SHA"]["CFG"]["MSGLEN_HI"]: [
        c_emu.shaengine.read_cfg_msglen_hi,
        c_emu.shaengine.write_cfg_msglen_hi,        
    ],
    KEYMGR_REGS["SHA"]["CFG"]["EN"]: [
        c_emu.shaengine.read_cfg_en,
        c_emu.shaengine.write_cfg_en,   
    ],
    KEYMGR_REGS["SHA"]["CFG"]["WR_EN"]: [
        c_emu.shaengine.read_cfg_wr_en,
        c_emu.shaengine.write_cfg_wr_en,   
    ],
    KEYMGR_REGS["SHA"]["TRIG"]: [
        c_emu.shaengine.read_trig,
        c_emu.shaengine.write_trig,   
    ],
    KEYMGR_REGS["SHA"]["INPUT_FIFO"]: [
        c_emu.shaengine.read_input_fifo,
        c_emu.shaengine.write_input_fifo,   
    ],
    KEYMGR_REGS["SHA"]["ITOP"]: [
        c_emu.shaengine.read_itop,
        c_emu.shaengine.write_itop,   
    ],
    KEYMGR_REGS["SHA"]["USE_CERT"]: [
        c_emu.shaengine.read_use_cert,
        c_emu.shaengine.write_use_cert,   
    ],
    KEYMGR_REGS["SHA"]["CERT_OVERRIDE"]: [
        c_emu.shaengine.read_cert_override,
        c_emu.shaengine.write_cert_override,
    ],
    KEYMGR_REGS["SHA"]["RAND_STALL_CTL"]: [
        c_emu.shaengine.read_rand_stall_ctl,
        c_emu.shaengine.write_rand_stall_ctl,
    ],
}

idx_regs_to_regmap(
    _REG_FUNC_MAP, KEYMGR_REGS["HKEY_RWR"],
    c_emu.read_hkey_rwr, c_emu.write_hkey_rwr
)

idx_regs_to_regmap(
    _REG_FUNC_MAP, KEYMGR_REGS["CERT_REVOKE_CTRL"],
    c_emu.read_cert_revoke_ctrl, c_emu.write_cert_revoke_ctrl
)

idx_retqueue_regs_to_regmap(
    _SHAENGINE_FUNC_MAP, KEYMGR_REGS["SHA"]["STS_H"],
    c_emu.shaengine.read_sts_h, c_emu.shaengine.write_sts_h
)

idx_retqueue_regs_to_regmap(
    _SHAENGINE_FUNC_MAP, KEYMGR_REGS["SHA"]["KEY_W"],
    c_emu.shaengine.read_key_w, c_emu.shaengine.write_key_w
)

# When we add the _SHAENGINE_FUNC_MAP to _REG_FUNC_MAP, we use a lambda to wrap
# around it to call it's respective queue function.
for k, v in _SHAENGINE_FUNC_MAP.items():
    _REG_FUNC_MAP[k] = [
        lambda size,
        v=v: c_emu.shaengine.queue_read_worker_op(v[0], size),
        lambda size, 
        value, 
        v=v: c_emu.shaengine.queue_write_worker_op(v[1], size, value),
    ]

def component_read_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    user_data: typing.Any,
) -> int:
    try:
        return _REG_FUNC_MAP[offset][0](size)
    except KeyError:
        unhandled_register_exit(prints, "KEYMGR0", offset)

def component_write_handler(
    uc: qemu.Uc,
    offset: int,
    size: int,
    value: int,
    user_data: typing.Any,
) -> None:
    try:
        _REG_FUNC_MAP[offset][1](size, value)
    except KeyError:
        unhandled_register_exit(prints, "KEYMGR0", offset)