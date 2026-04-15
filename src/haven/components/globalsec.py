# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

import typing
import unicorn as qemu

from lib.emulator_context import EmulatorContext, ComponentObjects
from env import *
from lib.logger import GscemuLogger
from lib.threadutils import FifoLock
from lib.helpers import (
    unhandled_register_io, 
    unhandled_register_exit,
    idx_regs_to_regmap,
    args_lambda_gen
)

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

PERMISSION_LOW = 0x00
PERMISSION_MEDIUM = 0x33
PERMISSION_HIGH = 0x3C
PERMISSION_HIGHEST = 0x55
_EXPECTED_SB_BL_SIG = [
    0xe303ec7a, 0x68a03a27, 0xdd18053e, 0x39f8dbbd, 
    0x9b553578, 0xb4598244, 0xc59f62d1, 0x61b8509e
]

class HavenGlobalsec:
    def __init__(self, ctx: EmulatorContext, regs: dict):
        self.ctx = ctx
        self.mutex = FifoLock()

        # HIDE_ROM doesn't do anything as far as we know, so don't do anything.
        self.hide_rom = 0 

        self.dbg_control = 0
        self.dummykey = [0] * 3

        self.sb_bl_sig = [0] * 8
        self.sb_comp_status = False

        self.obfs_sw_en = False

        self.permission_runlevel = {
            regs["CPU0_S_PERMISSION"]: PERMISSION_HIGHEST,
            regs["CPU0_S_DAP_PERMISSION"]: PERMISSION_HIGHEST,
            regs["DDMA0_PERMISSION"]: PERMISSION_HIGHEST,
            regs["SOFTWARE_LVL"]: PERMISSION_HIGHEST,
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

    def read_alert_cfg_lock(self, size: int) -> None:
        with self.mutex:
            return self.alert_cfg_lock

    def write_alert_cfg_lock(self, size: int, value: int) -> None:
        with self.mutex:
            self.alert_cfg_lock = value

    def read_alert_fw_trigger(self, size: int) -> None:
        with self.mutex:
            return self.alert_fw_trigger

    def write_alert_fw_trigger(self, size: int, value: int) -> None:
        with self.mutex:
            self.alert_fw_trigger = value

    def read_alert_control(self, size: int) -> None:
        with self.mutex:
            return self.alert_control

    def write_alert_control(self, size: int, value: int) -> None:
        with self.mutex:
            self.alert_control = value

    def read_alert_intr_sts(self, size: int, index: int) -> None:
        with self.mutex:
            return self.alert_intr_sts[index]

    def write_alert_intr_sts(
            self, size: int, value: int, index: int
        ) -> None:
        with self.mutex:
            self.alert_intr_sts[index] = value

    def read_alert_nmi_en(self, size: int, index: int) -> None:
        with self.mutex:
            return self.alert_nmi_en[index]

    def write_alert_nmi_en(
            self, size: int, value: int, index: int
        ) -> None:
        with self.mutex:
            self.alert_nmi_en[index] = value

    def read_alert_dlyctr_base(self, size: int, index: int) -> None:
        with self.mutex:
            return self.alert_dlyctr[index]["BASE"]

    def write_alert_dlyctr_base(
            self, size: int, value: int, index: int
        ) -> None:
        with self.mutex:
            self.alert_dlyctr[index]["BASE"] = value

    def read_alert_dlyctr_len(
            self, size: int, index: int
        ) -> None:
        with self.mutex:
            return self.alert_dlyctr[index]["LEN"]

    def write_alert_dlyctr_len(
            self, size: int, value: int, index: int
        ) -> None:
        with self.mutex:
            self.alert_dlyctr[index]["LEN"] = value

    def read_alert_dlyctr_en(self, size: int, index: int, en_index: int) -> None:
        with self.mutex:
            return self.alert_dlyctr[index]["EN"][en_index]

    def write_alert_dlyctr_en(
            self, size: int, value: int, index: int, en_index: int
        ) -> None:
        with self.mutex:
            self.alert_dlyctr[index]["EN"][en_index] = value

    def read_alert_dlyctr_shutdown_en(self, size: int, index: int) -> None:
        with self.mutex:
            return self.alert_dlyctr[index]["SHUTDOWN_EN"]

    def write_alert_dlyctr_shutdown_en(
            self, size: int, value: int, index: int
        ) -> None:
        with self.mutex:
            self.alert_dlyctr[index]["SHUTDOWN_EN"] = value

    def read_alert_dlyctr_clear(self, size: int, index: int) -> None:
        with self.mutex:
            return self.alert_dlyctr[index]["CLEAR"]

    def write_alert_dlyctr_clear(
            self, size: int, value: int, index: int
        ) -> None:
        with self.mutex:
            self.alert_dlyctr[index]["CLEAR"] = value

    def read_alert_group_en(self, size: int, index: int, en_index: int) -> None:
        with self.mutex:
            return self.alert_group[index]["EN"][en_index]

    def write_alert_group_en(
            self, size: int, value: int, index: int, en_index: int
        ) -> None:
        with self.mutex:
            self.alert_group[index]["EN"][en_index] = value

    def read_alert_group_ctr(self, size: int, index: int) -> None:
        with self.mutex:
            return self.alert_group[index]["CTR"]

    def write_alert_group_ctr(self, size: int, value: int, index: int) -> None:
        with self.mutex:
            self.alert_group[index]["CTR"] = value

    def read_alert_group_threshold(self, size: int, index: int) -> None:
        with self.mutex:
            return self.alert_group[index]["THRESHOLD"]

    def write_alert_group_threshold(
            self, size: int, value: int, index: int
        ) -> None:
        with self.mutex:
            self.alert_group[index]["THRESHOLD"] = value

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

    def read_permission_runlevel(self, size: int, reg_offset: int) -> None:
        with self.mutex:
            return self.permission_runlevel[reg_offset]

    def write_permission_runlevel(
            self, size: int, value: int, reg_offset: int
        ) -> None:
        with self.mutex:
            self.decrement_permission_runlevel(reg_offset)
        
    def read_dummykey(self, size: int, index: int) -> None:
        with self.mutex:
            return self.dummykey[index]

    def write_dummykey(self, size: int, value: int, index: int) -> None:
        with self.mutex:
            self.dummykey[index] = value

    def read_dbg_control(self, size: int) -> None:
        with self.mutex:
            return self.dbg_control

    def write_dbg_control(self, size: int, value: int) -> None:
        with self.mutex:
            self.dbg_control = value

    def read_sb_comp_status(self, size: int) -> None:
        with self.mutex:
            return int(self.sb_comp_status)

    def write_sb_comp_status(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "GLOBALSEC", "SB_COMP_STATUS")

    def read_sb_bl_sig(self, size: int, index: int) -> None:
        # We know that on a Cr50, reading from SB_BL_SIG returns a 0xfacecafe
        with self.mutex:
            return 0xfacecafe

    def write_sb_bl_sig(self, size: int, value: int, index: int) -> None:
        with self.mutex:
            self.sb_bl_sig[index] = value

    def read_sig_unlock(self, size: int) -> None:
        unhandled_register_io(prints, "READ", "GLOBALSEC", "SIG_UNLOCK")
        return 0

    def write_sig_unlock(self, size: int, value: int) -> None:
        with self.mutex:
            # System has requested for execution unlock. Verify SB_BL_SIG.
            if GSCEMULATOR_FORCE_SB_COMP_STATUS:
                self.sb_comp_status = True
                return

            if self.sb_bl_sig == _EXPECTED_SB_BL_SIG:
                self.sb_comp_status = True
            else:
                self.sb_comp_status = False

    def read_dbg_control(self, size: int) -> None:
        with self.mutex:
            return self.dbg_control

    def write_dbg_control(self, size: int, value: int) -> None:
        with self.mutex:
            self.dbg_control = value

    def read_hide_rom(self, size: int) -> None:
        with self.mutex:
            return self.hide_rom

    def write_hide_rom(self, size: int, value: int) -> None:
        with self.mutex:
            # We know that the Cr50 does not allow HIDE_ROM to change
            # after it has a value.
            if self.hide_rom:
                return
            self.hide_rom = value

    def read_obfs_sw_en(self, size: int) -> None:
        with self.mutex:
            return self.obfs_sw_en

    def write_obfs_sw_en(self, size: int, value: int) -> None:
        unhandled_register_io(prints, "WRITE", "GLOBALSEC", "OBFS_SW_EN")

    def read_region_register(
        self,
        size: int, 
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
            return value

    def write_region_register(
        self,
        size: int,
        value: int, 
        reg_type: str, 
        bus_master: str, 
        index: int
    ) -> None:
        with self.mutex:
            if reg_type == "ctrl":
                self.region_ctrl[bus_master][index] = value
            elif reg_type == "ctrl_cfg_en":
                self.region_ctrl_cfg_en[bus_master][index] = value
            elif reg_type == "base_addr":
                self.region_base_addr[bus_master][index] = value
            elif reg_type == "size":
                self.region_size[bus_master][index] = value

def init_HavenGlobalsec(ctx: EmulatorContext, regs: dict):
    c_emu = HavenGlobalsec(ctx, regs)

    reg_fn_map = {
        regs["DBG_CONTROL"]: [
            c_emu.read_dbg_control, c_emu.write_dbg_control,
        ],
        regs["ALERT"]["CFG_LOCK"]: [
            c_emu.read_alert_cfg_lock, c_emu.write_alert_cfg_lock
        ],
        regs["ALERT"]["FW_TRIGGER"]: [
            c_emu.read_alert_fw_trigger, c_emu.write_alert_fw_trigger
        ],
        regs["ALERT"]["CONTROL"]: [
            c_emu.read_alert_control, c_emu.write_alert_control
        ],
        regs["HIDE_ROM"]: [
            c_emu.read_hide_rom, c_emu.write_hide_rom
        ],
        regs["SIG_UNLOCK"]: [
            c_emu.read_sig_unlock, c_emu.write_sig_unlock
        ],
        regs["SB_COMP_STATUS"]: [
            c_emu.read_sb_comp_status, c_emu.write_sb_comp_status
        ],
        regs["OBFS_SW_EN"]: [
            c_emu.read_obfs_sw_en, c_emu.write_obfs_sw_en
        ],
    }

    # GLOBALSEC has many registers that repeat. We should dynamically add the
    # register handlers, not manually add them to the function map. This 
    # improves code readability and maintainability. We only sacrifice setup 
    # runtime, not emulator runtime. Setup runtime is mostly negligible.
    for reg_type in ["CTRL", "CTRL_CFG_EN", "BASE_ADDR", "SIZE"]:
        reg_type_lower = reg_type.lower()
        for bus_master, offsets in regs["REGION"][reg_type].items():
            for idx, offset in enumerate(offsets):
                reg_fn_map[offset] = [
                    args_lambda_gen(
                        c_emu.read_region_register,
                        reg_type_lower,
                        bus_master,
                        idx
                    ),
                    args_lambda_gen(
                        c_emu.write_region_register,
                        reg_type_lower,
                        bus_master,
                        idx
                    )
                ]

    idx_regs_to_regmap(
        reg_fn_map, regs["ALERT"]["INTR_STS"],
        c_emu.read_alert_intr_sts, c_emu.write_alert_intr_sts
    )

    idx_regs_to_regmap(
        reg_fn_map, regs["ALERT"]["NMI_EN"],
        c_emu.read_alert_nmi_en, c_emu.write_alert_nmi_en
    )

    for idx, dlyctr in enumerate(regs["ALERT"]["DLYCTR"]):
        reg_fn_map[dlyctr["BASE"]] = [
            args_lambda_gen(c_emu.read_alert_dlyctr_base, idx),
            args_lambda_gen(c_emu.write_alert_dlyctr_base, idx)
        ]
        reg_fn_map[dlyctr["LEN"]] = [
            args_lambda_gen(c_emu.read_alert_dlyctr_len, idx),
            args_lambda_gen(c_emu.write_alert_dlyctr_len, idx)
        ]
        for en_idx, en_offset in enumerate(dlyctr["EN"]):
            reg_fn_map[en_offset] = [
                args_lambda_gen(
                    c_emu.read_alert_dlyctr_en, idx, en_idx
                ),
                args_lambda_gen(
                    c_emu.write_alert_dlyctr_en, idx, en_idx
                )
            ]
        reg_fn_map[dlyctr["SHUTDOWN_EN"]] = [
            args_lambda_gen(c_emu.read_alert_dlyctr_shutdown_en, idx),
            args_lambda_gen(c_emu.write_alert_dlyctr_shutdown_en, idx)
        ]
        reg_fn_map[dlyctr["CLEAR"]] = [
            args_lambda_gen(c_emu.read_alert_dlyctr_clear, idx),
            args_lambda_gen(c_emu.write_alert_dlyctr_clear, idx)
        ]

    for idx, group in enumerate(regs["ALERT"]["GROUP"]):
        for en_idx, en_offset in enumerate(group["EN"]):
            reg_fn_map[en_offset] = [
                args_lambda_gen(
                    c_emu.read_alert_group_en, idx, en_idx
                ),
                args_lambda_gen(
                    c_emu.read_alert_group_en, idx, en_idx
                ),
            ]
        reg_fn_map[group["CTR"]] = [
            args_lambda_gen(c_emu.read_alert_group_ctr, idx),
            args_lambda_gen(c_emu.write_alert_group_ctr, idx)
        ]
        reg_fn_map[group["THRESHOLD"]] = [
            args_lambda_gen(c_emu.read_alert_group_threshold, idx),
            args_lambda_gen(c_emu.write_alert_group_threshold, idx)
        ]

    idx_regs_to_regmap(
        reg_fn_map, regs["DUMMYKEY"],
        c_emu.read_dummykey, c_emu.write_dummykey
    )

    idx_regs_to_regmap(
        reg_fn_map, regs["SB_BL_SIG"],
        c_emu.read_sb_bl_sig, c_emu.write_sb_bl_sig
    )

    for perm in [
        "CPU0_S_PERMISSION", "CPU0_S_DAP_PERMISSION", 
        "DDMA0_PERMISSION", "SOFTWARE_LVL"
    ]:
        reg_fn_map[regs[perm]] = [
            args_lambda_gen(
                c_emu.read_permission_runlevel, regs[perm]
            ),
            args_lambda_gen(
                c_emu.write_permission_runlevel, regs[perm]
            ),
        ]

    def component_read_handler(
        uc_unused: qemu.Uc,
        offset: int,
        size: int,
        user_data: typing.Any,
    ) -> int:
        try:
            return reg_fn_map[offset][0](size)
        except KeyError:
            unhandled_register_exit(ctx, prints, "GLOBALSEC", offset)

    def component_write_handler(
        uc_unused: qemu.Uc,
        offset: int,
        size: int,
        value: int,
        user_data: typing.Any,
    ) -> None:
        try:
            reg_fn_map[offset][1](size, value)
        except KeyError:
            unhandled_register_exit(ctx, prints, "GLOBALSEC", offset)

    return ComponentObjects(
        None, component_read_handler, component_write_handler
    )