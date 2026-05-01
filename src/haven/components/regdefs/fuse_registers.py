# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer
# ruff: noqa

"""File containing all the FUSE registers that exist on the current Cr50.

Including this into the main register file is not wise. This is a really long
list of registers. Therefore, seperate it into its own file.

All register values derived from
https://chromium.googlesource.com/chromiumos/platform/ec/+/a766634/chip/g/hw_regdefs.h
"""

FUSE_REGISTERS = {
    "BNK0_INTG_CHKSUM": 0x30,
    "BNK0_INTG_LOCK": 0x34,
    "DS_GRP0": 0x38,
    "DS_GRP1": 0x3c,
    "DS_GRP2": 0x40,
    "DEV_ID0": 0x44,
    "DEV_ID1": 0x48,
    "BNK1_INTG_CHKSUM": 0x4c,
    "BNK1_INTG_LOCK": 0x50,
    "LB0_POST_OVRD": 0x54,
    "LB0_POST_PATCNT": 0x58,
    "LB0_POST_WARMUP_OVRD": 0x5c,
    "LB0_POST_WARMUP_CNT": 0x60,
    "LB1_POST_OVRD": 0x64,
    "LB1_POST_PATCNT": 0x68,
    "LB1_POST_WARMUP_OVRD": 0x6c,
    "LB1_POST_WARMUP_CNT": 0x70,
    "LB2_POST_OVRD": 0x74,
    "LB2_POST_PATCNT": 0x78,
    "LB2_POST_WARMUP_OVRD": 0x7c,
    "LB2_POST_WARMUP_CNT": 0x80,
    "LB3_POST_OVRD": 0x84,
    "LB3_POST_PATCNT": 0x88,
    "LB3_POST_WARMUP_OVRD": 0x8c,
    "LB3_POST_WARMUP_CNT": 0x90,
    "LB4_POST_OVRD": 0x94,
    "LB4_POST_PATCNT": 0x98,
    "LB4_POST_WARMUP_OVRD": 0x9c,
    "LB4_POST_WARMUP_CNT": 0xa0,
    "MBIST_POST_SEQ": 0xa4,
    "LBIST_POST_SEQ": 0xa8,
    "LBIST_VIA_TAP_DIS": 0xac,
    "MBIST_VIA_TAP_DIS": 0xb0,
    "TAP_DISABLE": 0xb4,
    "RNGBIST_AR_EN": 0xb8,
    "TESTMODE_KEYS_EN": 0xbc,
    "PKG_ID": 0xc0,
    "BIN_ID": 0xc4,
    "RC_JTR_OSC48_CC_TRIM": 0xc8,
    "RC_JTR_OSC48_CC_EN": 0xcc,
    "RC_JTR_OSC60_CC_TRIM": 0xd0,
    "RC_JTR_OSC60_CC_EN": 0xd4,
    "RC_TIMER_OSC48_CC_TRIM": 0xd8,
    "RC_TIMER_OSC48_CC_EN": 0xdc,
    "RC_TIMER_OSC48_FC_TRIM": 0xe0,
    "RC_TIMER_OSC48_FC_EN": 0xe4,
    "RC_RTC_OSC256K_CC_TRIM": 0xe8,
    "RC_RTC_OSC256K_CC_EN": 0xec,
    "SEL_VREG_REG_EN": 0xf0,
    "SEL_VREF_REG": 0xf4,
    "SEL_VREF_BATMON_EN": 0xf8,
    "SEL_VREF_BATMON": 0xfc,
    "X_OSC_LDO_CTRL_EN": 0x100,
    "X_OSC_LDO_CTRL": 0x104,
    "TEMP_OFFSET_CAL": 0x108,
    "TRNG_LDO_CTRL_EN": 0x10c,
    "TRNG_LDO_CTRL": 0x110,
    "TRNG_ANALOG_CTRL_EN": 0x114,
    "TRNG_ANALOG_CTRL": 0x118,
    "EXT_XTAL_PDB": 0x11c,
    "DIS_EXT_XTAL_CLK_TREE": 0x120,
    "OBFUSCATION_EN": 0x124,
    "HIK_CREATE_LOCK": 0x128,
    "BNK2_INTG_CHKSUM": 0x12c,
    "BNK2_INTG_LOCK": 0x130,
    "TESTMODE_OTPW_DIS": 0x134,
    "HKEY_WDOG_TIMER_EN": 0x138,
    "FLASH_PERSO_PAGE_LOCK": 0x13c,
    "ALERT_RSP_CFG": 0x140,
    "BNK3_INTG_CHKSUM": 0x144,
    "BNK3_INTG_LOCK": 0x148,
    "FW_DEFINED_DATA_BLK0": 0x14c,
    "FW_DEFINED_BROM_ERR_RESPONSE": 0x150,
    "FW_DEFINED_BROM_APPLYSEC": 0x154,
    "FW_DEFINED_BROM_CONFIG0": 0x158,
    "FW_DEFINED_BROM_CONFIG1": 0x15c,
    "RBOX_MODE_DBG_OVRD_DIS": 0x160,
    "RBOX_MODE_OUTPUT_OVRD_DIS": 0x164,
    "RBOX_CLK10HZ_COUNT": 0x168,
    "RBOX_SHORT_DELAY_COUNT": 0x16c,
    "RBOX_LONG_DELAY_COUNT": 0x170,
    "RBOX_DEBOUNCE_PERIOD": 0x174,
    "RBOX_DEBOUNCE_BYPASS_PWRB": 0x178,
    "RBOX_DEBOUNCE_BYPASS_KEY0": 0x17c,
    "RBOX_DEBOUNCE_BYPASS_KEY1": 0x180,
    "RBOX_KEY_COMBO0_VAL": 0x184,
    "RBOX_KEY_COMBO1_VAL": 0x188,
    "RBOX_KEY_COMBO2_VAL": 0x18c,
    "RBOX_KEY_COMBO0_HOLD": 0x190,
    "RBOX_KEY_COMBO1_HOLD": 0x194,
    "RBOX_KEY_COMBO2_HOLD": 0x198,
    "RBOX_BLOCK_KEY0_SEL": 0x19c,
    "RBOX_BLOCK_KEY1_SEL": 0x1a0,
    "RBOX_BLOCK_KEY0_VAL": 0x1a4,
    "RBOX_BLOCK_KEY1_VAL": 0x1a8,
    "RBOX_POL_AC_PRESENT": 0x1ac,
    "RBOX_POL_PWRB_IN": 0x1b0,
    "RBOX_POL_PWRB_OUT": 0x1b4,
    "RBOX_POL_KEY0_IN": 0x1b8,
    "RBOX_POL_KEY0_OUT": 0x1bc,
    "RBOX_POL_KEY1_IN": 0x1c0,
    "RBOX_POL_KEY1_OUT": 0x1c4,
    "RBOX_POL_EC_RST": 0x1c8,
    "RBOX_POL_BATT_DISABLE": 0x1cc,
    "RBOX_TERM_AC_PRESENT": 0x1d0,
    "RBOX_TERM_ENTERING_RW": 0x1d4,
    "RBOX_TERM_PWRB_IN": 0x1d8,
    "RBOX_TERM_PWRB_OUT": 0x1dc,
    "RBOX_TERM_KEY0_IN": 0x1e0,
    "RBOX_TERM_KEY0_OUT": 0x1e4,
    "RBOX_TERM_KEY1_IN": 0x1e8,
    "RBOX_TERM_KEY1_OUT": 0x1ec,
    "RBOX_DRIVE_PWRB_OUT": 0x1f0,
    "RBOX_DRIVE_KEY0_OUT": 0x1f4,
    "RBOX_DRIVE_KEY1_OUT": 0x1f8,
    "RBOX_DRIVE_EC_RST": 0x1fc,
    "RBOX_DRIVE_BATT_DISABLE": 0x200,
    "BNK4_INTG_CHKSUM": 0x204,
    "BNK4_INTG_LOCK": 0x208,
    "FW_DEFINED_DATA_EXTRA_BLK0": 0x20c,
    "FW_DEFINED_DATA_EXTRA_BLK1": 0x210,
    "FW_DEFINED_DATA_EXTRA_BLK2": 0x214,
    "FW_DEFINED_DATA_EXTRA_BLK3": 0x218,
    "FW_DEFINED_DATA_EXTRA_BLK4": 0x21c,
    "FW_DEFINED_DATA_EXTRA_BLK5": 0x220,
    "FW_DEFINED_DATA_EXTRA_BLK6": 0x224,
}

FUSE_DEFAULTS = {
    FUSE_REGISTERS["DEV_ID0"]: 0x300903c,
    FUSE_REGISTERS["DEV_ID1"]: 0x942bce84,

    FUSE_REGISTERS["RC_JTR_OSC48_CC_EN"]: 0x55555555,
    FUSE_REGISTERS["RC_JTR_OSC60_CC_EN"]: 0x55555555,

    FUSE_REGISTERS["RC_JTR_OSC48_CC_TRIM"]: 0x55555544,
    FUSE_REGISTERS["RC_JTR_OSC60_CC_TRIM"]: 0x5555552c,
    FUSE_REGISTERS["RC_RTC_OSC256K_CC_TRIM"]: 0x555555f0,
    FUSE_REGISTERS["RC_TIMER_OSC48_CC_TRIM"]: 0x55555548,
    FUSE_REGISTERS["RC_TIMER_OSC48_FC_TRIM"]: 0x55555550,

    FUSE_REGISTERS["RBOX_KEY_COMBO0_VAL"]: 0x555555c0,
    FUSE_REGISTERS["RBOX_KEY_COMBO0_HOLD"]: 0x55555500,
    FUSE_REGISTERS["RBOX_POL_KEY1_IN"]: 0x55555555,

    FUSE_REGISTERS["OBFUSCATION_EN"]: 0x55555550,

    FUSE_REGISTERS["TRNG_LDO_CTRL_EN"]: 0x55555555,
    FUSE_REGISTERS["TRNG_LDO_CTRL"]: 0x5555554e,
    FUSE_REGISTERS["TRNG_ANALOG_CTRL_EN"]: 0x55555555,

    FUSE_REGISTERS["FW_DEFINED_BROM_ERR_RESPONSE"]: 0x5555f1ff,
    FUSE_REGISTERS["FW_DEFINED_BROM_CONFIG0"]: 0x55555506,
    FUSE_REGISTERS["FW_DEFINED_BROM_CONFIG1"]: 0x55555500,
    FUSE_REGISTERS["FW_DEFINED_BROM_APPLYSEC"]: 0x55555137,

    # expected values on the Cr50, these are correct, DO NOT TOUCH. Hfss will fail if this is modified.
    FUSE_REGISTERS["FLASH_PERSO_PAGE_LOCK"]: 0x55555555,
    FUSE_REGISTERS["FW_DEFINED_DATA_BLK0"]: 0x55555502,
    FUSE_REGISTERS["FW_DEFINED_DATA_EXTRA_BLK6"]: 0x55555540,

    # the Cr50 will crash with an assertion error if this is not 0x5
    FUSE_REGISTERS["RC_RTC_OSC256K_CC_EN"]: 0x55555555,
}

# very minimal fuse values.
# MINIMAL_FUSE_VALUES = {
#     # expected values on the Cr50, these are correct, DO NOT TOUCH
#     "FLASH_PERSO_PAGE_LOCK": 0x55555555,
#     "FW_DEFINED_DATA_BLK0": 0x55555502,
#     "FW_DEFINED_DATA_EXTRA_BLK6": 0x55555540,

#     # the Cr50 will crash with an assertion error if this is not 0x5
#     "RC_RTC_OSC256K_CC_EN": 0x55555555,
# }

#  from Cr50 source code:
#
#  There are three versions of B2 H1s outhere in the wild so far: chromebook,
#  poppy and detachable. The following registers are different in those
#  three versions in the following way:

#    register                chromebook          poppy     detachable
# --------------------------------------------------------------------
#  RBOX_KEY_COMBO0_VAL          0xc0             0x80        0xc0
#  RBOX_POL_KEY1_IN             0x01             0x00        0x00
#  RBOX_KEY_COMBO0_HOLD         0x00             0x00        0x59
