# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import unicorn as qemu

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from lib.threadutils import FifoLock
from src.emulators.haven.registers import REG_DEFS, GLOBALSEC_REGS
from lib.helpers import unhandled_register_io, unhandled_register_exit

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

PERMISSION_LOW = 0x00
PERMISSION_MEDIUM = 0x33
PERMISSION_HIGH = 0x3C
PERMISSION_HIGHEST = 0x55
_EXPECTED_SB_BL_SIG = [
    0xe303ec7a, 0x68a03a27, 0xdd18053e, 0x39f8dbbd, 
    0x9b553578, 0xb4598244, 0xc59f62d1, 0x61b8509e
]
_REG_BASE_ADDR = REG_DEFS["GLOBALSEC"]["base_addr"]

class HavenGlobalsec:
    def __init__(self):
        self.mutex = FifoLock()

        # HIDE_ROM doesn't do anything as far as we know, so don't do anything.
        self.hide_rom = 0 

        self.dbg_control = 0
        self.dummykey = [0] * 3

        self.sb_bl_sig = [0] * 8
        self.sb_comp_status = False

        self.permission_runlevel = {
            GLOBALSEC_REGS["CPU0_S_PERMISSION"]: PERMISSION_HIGHEST,
            GLOBALSEC_REGS["CPU0_S_DAP_PERMISSION"]: PERMISSION_HIGHEST,
            GLOBALSEC_REGS["DDMA0_PERMISSION"]: PERMISSION_HIGHEST,
            GLOBALSEC_REGS["SOFTWARE_LVL"]: PERMISSION_HIGHEST,
        }

        self.region_ctrl = {
            "CPU0_D": [0] * 8,
            "CPU0_D_DAP": [0] * 4,
            "CPU0_I": [0] * 8,
            "DDMA0": [0] * 4,
            "DSPS0": [0] * 4,
            "DUSB0": [0] * 4,
            "FLASH": [0] * 8,
            "FLASH0_BULKERASE": [0],
            "FLASH1_BULKERASE": [0],
            "CPU0_I_STAGING": [0] * 8,
        }

        self.region_ctrl_cfg_en = {
            "CPU0_D": [0] * 8,
            "CPU0_D_DAP": [0] * 4,
            "DDMA0": [0] * 4,
            "DSPS0": [0] * 4,
            "DUSB0": [0] * 4,
            "FLASH": [0] * 8,
            "FLASH0_BULKERASE": [0],
            "FLASH1_BULKERASE": [0],
        }

        self.region_base_addr = {
            "CPU0_D": [0] * 8,
            "CPU0_D_DAP": [0] * 4,
            "CPU0_I": [0] * 8,
            "DDMA0": [0] * 4,
            "DSPS0": [0] * 4,
            "DUSB0": [0] * 4,
            "FLASH": [0] * 8,
            "CPU0_I_STAGING": [0] * 8,
        }

        self.region_size = {
            "CPU0_D": [0] * 8,
            "CPU0_D_DAP": [0] * 4,
            "CPU0_I": [0] * 8,
            "DDMA0": [0] * 4,
            "DSPS0": [0] * 4,
            "DUSB0": [0] * 4,
            "FLASH": [0] * 8,
            "CPU0_I_STAGING": [0] * 8,
        }

        self.alert_cfg_lock = 0
        self.alert_fw_trigger = 0
        self.alert_control = 0
        self.alert_intr_sts = [0] * 2
        self.alert_nmi_en = [0] * 2

        self.alert_dlyctr = [
            {
                "BASE": 0,
                "LEN": 0,
                "EN": [0] * 2,
                "SHUTDOWN_EN": 0,
                "CLEAR": 0,
            } for _ in range(3)
        ]

        self.alert_group = [
            {
                "EN": [0] * 2,
                "CTR": 0,
                "THRESHOLD": 0,
            } for _ in range(3)
        ]

    def read_alert_cfg_lock(self, addr: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(addr, self.alert_cfg_lock)

    def write_alert_cfg_lock(self, val: int) -> None:
        with self.mutex:
            self.alert_cfg_lock = val

    def read_alert_fw_trigger(self, addr: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(addr, self.alert_fw_trigger)

    def write_alert_fw_trigger(self, val: int) -> None:
        with self.mutex:
            self.alert_fw_trigger = val

    def read_alert_control(self, addr: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(addr, self.alert_control)

    def write_alert_control(self, val: int) -> None:
        with self.mutex:
            self.alert_control = val

    def read_alert_intr_sts(self, addr: int, index: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(addr, self.alert_intr_sts[index])

    def write_alert_intr_sts(self, val: int, index: int) -> None:
        with self.mutex:
            self.alert_intr_sts[index] = val

    def read_alert_nmi_en(self, addr: int, index: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(addr, self.alert_nmi_en[index])

    def write_alert_nmi_en(self, val: int, index: int) -> None:
        with self.mutex:
            self.alert_nmi_en[index] = val

    def read_alert_dlyctr_base(self, addr: int, index: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(
                addr, self.alert_dlyctr[index]["BASE"]
            )

    def write_alert_dlyctr_base(self, val: int, index: int) -> None:
        with self.mutex:
            self.alert_dlyctr[index]["BASE"] = val

    def read_alert_dlyctr_len(self, addr: int, index: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(
                addr, self.alert_dlyctr[index]["LEN"]
            )

    def write_alert_dlyctr_len(self, val: int, index: int) -> None:
        with self.mutex:
            self.alert_dlyctr[index]["LEN"] = val

    def read_alert_dlyctr_en(self, addr: int, index: int, en_index: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(
                addr, self.alert_dlyctr[index]["EN"][en_index]
            )

    def write_alert_dlyctr_en(self, val: int, index: int, en_index: int) -> None:
        with self.mutex:
            self.alert_dlyctr[index]["EN"][en_index] = val

    def read_alert_dlyctr_shutdown_en(self, addr: int, index: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(
                addr, self.alert_dlyctr[index]["SHUTDOWN_EN"]
            )

    def write_alert_dlyctr_shutdown_en(self, val: int, index: int) -> None:
        with self.mutex:
            self.alert_dlyctr[index]["SHUTDOWN_EN"] = val

    def read_alert_dlyctr_clear(self, addr: int, index: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(
                addr, self.alert_dlyctr[index]["CLEAR"]
            )

    def write_alert_dlyctr_clear(self, val: int, index: int) -> None:
        with self.mutex:
            self.alert_dlyctr[index]["CLEAR"] = val

    def read_alert_group_en(self, addr: int, index: int, en_index: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(
                addr, self.alert_group[index]["EN"][en_index]
            )

    def write_alert_group_en(self, val: int, index: int, en_index: int) -> None:
        with self.mutex:
            self.alert_group[index]["EN"][en_index] = val

    def read_alert_group_ctr(self, addr: int, index: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(
                addr, self.alert_group[index]["CTR"]
            )

    def write_alert_group_ctr(self, val: int, index: int) -> None:
        with self.mutex:
            self.alert_group[index]["CTR"] = val

    def read_alert_group_threshold(self, addr: int, index: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(
                addr, self.alert_group[index]["THRESHOLD"]
            )

    def write_alert_group_threshold(self, val: int, index: int) -> None:
        with self.mutex:
            self.alert_group[index]["THRESHOLD"] = val

    def decrement_permission_runlevel(self, reg_offset: int) -> None:
        curr_runlevel = self.permission_runlevel[reg_offset]

        if curr_runlevel == PERMISSION_HIGHEST:
            curr_runlevel = PERMISSION_HIGH

        elif curr_runlevel == PERMISSION_HIGH:
            curr_runlevel = PERMISSION_MEDIUM

        elif curr_runlevel == PERMISSION_MEDIUM:
            curr_runlevel = PERMISSION_LOW

        elif curr_runlevel == PERMISSION_LOW:
            return

        self.permission_runlevel[reg_offset] = curr_runlevel

    def read_permission_runlevel(self, reg_offset: int, addr: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(
                addr, self.permission_runlevel[reg_offset]
            )

    def write_permission_runlevel(self, reg_offset: int, val: int) -> None:
        with self.mutex:
            self.decrement_permission_runlevel(reg_offset)
        
    def read_dummykey(self, addr: int, idx: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(addr, self.dummykey[idx])

    def write_dummykey(self, val: int, idx: int) -> None:
        with self.mutex:
            self.dummykey[idx] = val

    def read_dbg_control(self, addr: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(addr, self.dbg_control)

    def write_dbg_control(self, val: int) -> None:
        with self.mutex:
            self.dbg_control = val

    def read_sb_comp_status(self, addr: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(addr, int(self.sb_comp_status))

    def write_sb_comp_status(self, val: int) -> None:
        with self.mutex:
            unhandled_register_io(
                prints, "WRITE", "GLOBALSEC", "SB_COMP_STATUS"
            )

    def read_sb_bl_sig(self, addr: int) -> None:
        # We know that on a Cr50, reading from SB_BL_SIG returns a 0xfacecafe
        with self.mutex:
            ucmutex().int32_mem_write(addr, 0xfacecafe)

    def write_sb_bl_sig(self, val: int, index: int) -> None:
        with self.mutex:
            self.sb_bl_sig[index] = val

    def read_sig_unlock(self, addr: int) -> None:
        with self.mutex:
            unhandled_register_io(prints, "READ", "GLOBALSEC", "SIG_UNLOCK")
            ucmutex().int32_mem_write(addr, 0)

    def write_sig_unlock(self, val: int) -> None:
        with self.mutex:
            # System has requested for execution unlock. Verify SB_BL_SIG.

            if self.sb_bl_sig == _EXPECTED_SB_BL_SIG:
                self.sb_comp_status = True
            else:
                self.sb_comp_status = False

    def read_dbg_control(self, addr: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(addr, self.dbg_control)

    def write_dbg_control(self, val: int) -> None:
        with self.mutex:
            self.dbg_control = val

    def read_hide_rom(self, addr: int) -> None:
        with self.mutex:
            ucmutex().int32_mem_write(addr, self.hide_rom)

    def write_hide_rom(self, val: int) -> None:
        with self.mutex:
            # We know that the Cr50 does not allow HIDE_ROM to change
            # after it has a value.
            if self.hide_rom:
                return
            self.hide_rom = val

    def read_region_register(self, 
                             addr: int, 
                             reg_type: str, 
                             bus_master: str, 
                             index: int
                             ) -> None:
        with self.mutex:
            if reg_type == "ctrl":
                value = self.region_ctrl[bus_master][index]
            elif reg_type == "ctrl_cfg_en":
                value = self.region_ctrl_cfg_en[bus_master][index]
            elif reg_type == "base_addr":
                value = self.region_base_addr[bus_master][index]
            elif reg_type == "size":
                value = self.region_size[bus_master][index]
            ucmutex().int32_mem_write(addr, value)

    def write_region_register(self, 
                              val: int, 
                              reg_type: str, 
                              bus_master: str, 
                              index: int
                              ) -> None:
        with self.mutex:
            if reg_type == "ctrl":
                self.region_ctrl[bus_master][index] = val
            elif reg_type == "ctrl_cfg_en":
                self.region_ctrl_cfg_en[bus_master][index] = val
            elif reg_type == "base_addr":
                self.region_base_addr[bus_master][index] = val
            elif reg_type == "size":
                self.region_size[bus_master][index] = val

c_emu = HavenGlobalsec()

_REG_FUNC_MAP = {
    GLOBALSEC_REGS["DBG_CONTROL"]: [
        c_emu.read_dbg_control, c_emu.write_dbg_control,
    ],
    GLOBALSEC_REGS["ALERT"]["CFG_LOCK"]: [
        c_emu.read_alert_cfg_lock, c_emu.write_alert_cfg_lock
    ],
    GLOBALSEC_REGS["ALERT"]["FW_TRIGGER"]: [
        c_emu.read_alert_fw_trigger, c_emu.write_alert_fw_trigger
    ],
    GLOBALSEC_REGS["ALERT"]["CONTROL"]: [
        c_emu.read_alert_control, c_emu.write_alert_control
    ],
    GLOBALSEC_REGS["CPU0_S_PERMISSION"]: [
        lambda addr, reg_offset=GLOBALSEC_REGS["CPU0_S_PERMISSION"]: 
        c_emu.read_permission_runlevel(reg_offset, addr),
        lambda val, reg_offset=GLOBALSEC_REGS["CPU0_S_PERMISSION"]: 
        c_emu.write_permission_runlevel(reg_offset, val),
    ],
    GLOBALSEC_REGS["CPU0_S_DAP_PERMISSION"]: [
        lambda addr, reg_offset=GLOBALSEC_REGS["CPU0_S_DAP_PERMISSION"]: 
        c_emu.read_permission_runlevel(reg_offset, addr),
        lambda val, reg_offset=GLOBALSEC_REGS["CPU0_S_DAP_PERMISSION"]: 
        c_emu.write_permission_runlevel(reg_offset, val),
    ],
    GLOBALSEC_REGS["DDMA0_PERMISSION"]: [
        lambda addr, reg_offset=GLOBALSEC_REGS["DDMA0_PERMISSION"]: 
        c_emu.read_permission_runlevel(reg_offset, addr),
        lambda val, reg_offset=GLOBALSEC_REGS["DDMA0_PERMISSION"]: 
        c_emu.write_permission_runlevel(reg_offset, val),
    ],
    GLOBALSEC_REGS["SOFTWARE_LVL"]: [
        lambda addr, reg_offset=GLOBALSEC_REGS["SOFTWARE_LVL"]: 
        c_emu.read_permission_runlevel(reg_offset, addr),
        lambda val, reg_offset=GLOBALSEC_REGS["SOFTWARE_LVL"]: 
        c_emu.write_permission_runlevel(reg_offset, val),
    ],

    GLOBALSEC_REGS["HIDE_ROM"]: [
        c_emu.read_hide_rom, c_emu.write_hide_rom
    ],
    GLOBALSEC_REGS["SIG_UNLOCK"]: [
        c_emu.read_sig_unlock, c_emu.write_sig_unlock
    ],
    GLOBALSEC_REGS["SB_COMP_STATUS"]: [
        c_emu.read_sb_comp_status, c_emu.write_sb_comp_status
    ],
}

# GLOBALSEC has many registers that repeat. We should dynamically add the
# register handlers, not manually add them to the function map. This improves
# code readability and maintainability. We only sacrifice setup runtime, not
# emulator runtime.
for reg_type in ["CTRL", "CTRL_CFG_EN", "BASE_ADDR", "SIZE"]:
    reg_type_lower = reg_type.lower()
    for bus_master, offsets in GLOBALSEC_REGS["REGION"][reg_type].items():
        for idx, offset in enumerate(offsets):
            _REG_FUNC_MAP[offset] = [
                lambda addr, 
                rt=reg_type_lower, 
                bm=bus_master, 
                i=idx: c_emu.read_region_register(addr, rt, bm, i),
                lambda val, 
                rt=reg_type_lower, 
                bm=bus_master, 
                i=idx: c_emu.write_region_register(val, rt, bm, i)
            ]

for idx, offset in enumerate(GLOBALSEC_REGS["ALERT"]["INTR_STS"]):
    _REG_FUNC_MAP[offset] = [
        lambda addr, i=idx: c_emu.read_alert_intr_sts(addr, i),
        lambda val, i=idx: c_emu.write_alert_intr_sts(val, i)
    ]

for idx, offset in enumerate(GLOBALSEC_REGS["ALERT"]["NMI_EN"]):
    _REG_FUNC_MAP[offset] = [
        lambda addr, i=idx: c_emu.read_alert_nmi_en(addr, i),
        lambda val, i=idx: c_emu.write_alert_nmi_en(val, i)
    ]

for idx, dlyctr in enumerate(GLOBALSEC_REGS["ALERT"]["DLYCTR"]):
    _REG_FUNC_MAP[dlyctr["BASE"]] = [
        lambda addr, i=idx: c_emu.read_alert_dlyctr_base(addr, i),
        lambda val, i=idx: c_emu.write_alert_dlyctr_base(val, i)
    ]
    _REG_FUNC_MAP[dlyctr["LEN"]] = [
        lambda addr, i=idx: c_emu.read_alert_dlyctr_len(addr, i),
        lambda val, i=idx: c_emu.write_alert_dlyctr_len(val, i)
    ]
    for en_idx, en_offset in enumerate(dlyctr["EN"]):
        _REG_FUNC_MAP[en_offset] = [
            lambda addr, 
            i=idx, 
            ei=en_idx: c_emu.read_alert_dlyctr_en(addr, i, ei),
            lambda val, 
            i=idx, 
            ei=en_idx: c_emu.write_alert_dlyctr_en(val, i, ei)
        ]
    _REG_FUNC_MAP[dlyctr["SHUTDOWN_EN"]] = [
        lambda addr, i=idx: c_emu.read_alert_dlyctr_shutdown_en(addr, i),
        lambda val, i=idx: c_emu.write_alert_dlyctr_shutdown_en(val, i)
    ]
    _REG_FUNC_MAP[dlyctr["CLEAR"]] = [
        lambda addr, i=idx: c_emu.read_alert_dlyctr_clear(addr, i),
        lambda val, i=idx: c_emu.write_alert_dlyctr_clear(val, i)
    ]

for idx, group in enumerate(GLOBALSEC_REGS["ALERT"]["GROUP"]):
    for en_idx, en_offset in enumerate(group["EN"]):
        _REG_FUNC_MAP[en_offset] = [
            lambda addr, 
            i=idx, 
            ei=en_idx: c_emu.read_alert_group_en(addr, i, ei),
            lambda val, 
            i=idx, 
            ei=en_idx: c_emu.write_alert_group_en(val, i, ei)
        ]
    _REG_FUNC_MAP[group["CTR"]] = [
        lambda addr, i=idx: c_emu.read_alert_group_ctr(addr, i),
        lambda val, i=idx: c_emu.write_alert_group_ctr(val, i)
    ]
    _REG_FUNC_MAP[group["THRESHOLD"]] = [
        lambda addr, i=idx: c_emu.read_alert_group_threshold(addr, i),
        lambda val, i=idx: c_emu.write_alert_group_threshold(val, i)
    ]

for idx, offset in enumerate(GLOBALSEC_REGS["DUMMYKEY"]):
    _REG_FUNC_MAP[offset] = [
        lambda addr, i=idx: c_emu.read_dummykey(addr, i),
        lambda val, i=idx: c_emu.write_dummykey(val, i)
    ]

for idx, offset in enumerate(GLOBALSEC_REGS["SB_BL_SIG"]):
    _REG_FUNC_MAP[offset] = [
        lambda addr, i=idx: c_emu.read_sb_bl_sig(addr, i),
        lambda val, i=idx: c_emu.write_sb_bl_sig(val, i)
    ]

def component_handler(
    uc: qemu.Uc,
    access,
    address: int,
    size: int,
    value: int,
    user_data
) -> bool:
    """Main component handler for GLOBALSEC"""

    reg_offset = address - _REG_BASE_ADDR

    try:
        if access == qemu.UC_MEM_READ:
            _REG_FUNC_MAP[reg_offset][0](address)
        elif access == qemu.UC_MEM_WRITE:
            _REG_FUNC_MAP[reg_offset][1](value)

    except KeyError:
        unhandled_register_exit(prints, "GLOBALSEC", address)