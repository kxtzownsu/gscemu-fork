# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

from lib.globalvars import *
from lib.helpers import pattern_list_gen as reg_list

PINMUX_SEL_REGS = {
    # These have both SEL + CTL registers, in [SEL | CTL] order
    "DIOM_SEL": reg_list(0x0, 5, 8),
    "DIOA_SEL": reg_list(0x28, 15, 8),
    "DIOB_SEL": reg_list(0xa0, 8, 8),
    "RESETB_SEL": 0xe0,
    "VIO_SEL": reg_list(0xe8, 2, 8),
    
    # These only have CTL components, as the "SEL" is controlled by the
    # component itself.
    "GPIO0_SEL": reg_list(0xf8, 16),
    "GPIO1_SEL": reg_list(0x138, 16),

    # -- gscemulator doesn't emulate these --
    "I2C0_SCL_SEL": 0x178,
    "I2C0_SDA_SEL": 0x17c,
    "I2C1_SCL_SEL": 0x180,
    "I2C1_SDA_SEL": 0x184,
    "I2CS0_SCL_SEL": 0x188,
    "I2CS0_SDA_SEL": 0x18c,

    "PMU_BROWNOUT_DET_SEL": 0x190,
    "PMU_TESTBUS_SEL": reg_list(0x194, 8),

    "RTC0_RTC_CLK_TEST_SEL": 0x1b4,

    "SPI1_SPICLK_SEL": 0x1b8,
    "SPI1_SPICSB_SEL": 0x1bc,
    "SPI1_SPIMISO_SEL": 0x1c0,
    "SPI1_SPIMOSI_SEL": 0x1c4,

    "SPS0_TESTBUS_SEL": reg_list(0x1c8, 8),

    "TEMP0_TST_ADC_CLK_SEL": 0x1e8,
    "TEMP0_TST_ADC_HI_SER_SEL": 0x1ec,
    "TEMP0_TST_ADC_LO_SER_SEL": 0x1f0,
    "TEMP0_TST_ADC_VLD_SER_SEL": 0x1f4,

    "TRNG0_TRNG_RO_DIV_SEL": 0x1f8,
    "TRNG0_TRNG_RO_REF_DIV_SEL": 0x1fc,

    "UART0_CTS_SEL": 0x200,
    "UART0_RTS_SEL": 0x204,
    "UART0_RX_SEL": 0x208,
    "UART0_TX_SEL": 0x20c,

    "UART1_CTS_SEL": 0x210,
    "UART1_RTS_SEL": 0x214,
    "UART1_RX_SEL": 0x218,
    "UART1_TX_SEL": 0x21c,

    "UART2_CTS_SEL": 0x220,
    "UART2_RTS_SEL": 0x224,
    "UART2_RX_SEL": 0x228,
    "UART2_TX_SEL": 0x22c,

    "USB0_EXT_DM_PULLUP_EN_SEL": 0x230,
    "USB0_EXT_DP_RPU1_ENB_SEL": 0x234,
    "USB0_EXT_DP_RPU2_ENB_SEL": 0x238,
    "USB0_EXT_FS_EDGE_SEL_SEL": 0x23c,
    "USB0_EXT_RX_DMI_SEL": 0x240,
    "USB0_EXT_RX_DPI_SEL": 0x244,
    "USB0_EXT_RX_RCV_SEL": 0x248,
    "USB0_EXT_SUSPENDB_SEL": 0x24c,
    "USB0_EXT_TX_DMO_SEL": 0x250,
    "USB0_EXT_TX_DPO_SEL": 0x254,
    "USB0_EXT_TX_OEB_SEL": 0x258,

    "VOLT0_TST_NEG_GLITCH_DET_SEL": 0x25c,
    "VOLT0_TST_POS_GLITCH_DET_SEL": 0x260,

    "XO0_TESTBUS_SEL": reg_list(0x264, 8),
}

PINMUX_SEL_VAL = {
    "DIOM0_SEL": 0x1e,
    "DIOM1_SEL": 0x1d,
    "DIOM2_SEL": 0x1c,
    "DIOM3_SEL": 0x1b,
    "DIOM4_SEL": 0x1a,

    "DIOA0_SEL": 0x19,
    "DIOA1_SEL": 0x18,
    "DIOA2_SEL": 0x17,
    "DIOA3_SEL": 0x16,
    "DIOA4_SEL": 0x15,
    "DIOA5_SEL": 0x14,
    "DIOA6_SEL": 0x13,
    "DIOA7_SEL": 0x12,
    "DIOA8_SEL": 0x11,
    "DIOA9_SEL": 0x10,
    "DIOA10_SEL": 0xf,
    "DIOA11_SEL": 0xe,
    "DIOA12_SEL": 0xd,
    "DIOA13_SEL": 0xc,
    "DIOA14_SEL": 0xb,

    "DIOB0_SEL": 0xa,
    "DIOB1_SEL": 0x9,
    "DIOB2_SEL": 0x8,
    "DIOB3_SEL": 0x7,
    "DIOB4_SEL": 0x6,
    "DIOB5_SEL": 0x5,
    "DIOB6_SEL": 0x4,
    "DIOB7_SEL": 0x3,

    "VIO0_SEL": 0x2,
    "VIO1_SEL": 0x1,

    "GPIO0_GPIO0_SEL": 0x1,
    "GPIO0_GPIO1_SEL": 0x2,
    "GPIO0_GPIO2_SEL": 0x3,
    "GPIO0_GPIO3_SEL": 0x4,
    "GPIO0_GPIO4_SEL": 0x5,
    "GPIO0_GPIO5_SEL": 0x6,
    "GPIO0_GPIO6_SEL": 0x7,
    "GPIO0_GPIO7_SEL": 0x8,
    "GPIO0_GPIO8_SEL": 0x9,
    "GPIO0_GPIO9_SEL": 0xa,
    "GPIO0_GPIO10_SEL": 0xb,
    "GPIO0_GPIO11_SEL": 0xc,
    "GPIO0_GPIO12_SEL": 0xd,
    "GPIO0_GPIO13_SEL": 0xe,
    "GPIO0_GPIO14_SEL": 0xf,
    "GPIO0_GPIO15_SEL": 0x10,

    "GPIO1_GPIO0_SEL": 0x11,
    "GPIO1_GPIO1_SEL": 0x12,
    "GPIO1_GPIO2_SEL": 0x13,
    "GPIO1_GPIO3_SEL": 0x14,
    "GPIO1_GPIO4_SEL": 0x15,
    "GPIO1_GPIO5_SEL": 0x16,
    "GPIO1_GPIO6_SEL": 0x17,
    "GPIO1_GPIO7_SEL": 0x18,
    "GPIO1_GPIO8_SEL": 0x19,
    "GPIO1_GPIO9_SEL": 0x1a,
    "GPIO1_GPIO10_SEL": 0x1b,
    "GPIO1_GPIO11_SEL": 0x1c,
    "GPIO1_GPIO12_SEL": 0x1d,
    "GPIO1_GPIO13_SEL": 0x1e,
    "GPIO1_GPIO14_SEL": 0x1f,
    "GPIO1_GPIO15_SEL": 0x20,

    "I2C0_SCL_SEL": 0x21,
    "I2C0_SDA_SEL": 0x22,
    "I2C1_SCL_SEL": 0x23,
    "I2C1_SDA_SEL": 0x24,

    "I2CS0_SCL_SEL": 0x25,
    "I2CS0_SDA_SEL": 0x26,

    "PMU_BROWNOUT_DET_SEL": 0x27,
    "PMU_TESTBUS0_SEL": 0x28,
    "PMU_TESTBUS1_SEL": 0x29,
    "PMU_TESTBUS2_SEL": 0x2a,
    "PMU_TESTBUS3_SEL": 0x2b,
    "PMU_TESTBUS4_SEL": 0x2c,
    "PMU_TESTBUS5_SEL": 0x2d,
    "PMU_TESTBUS6_SEL": 0x2e,
    "PMU_TESTBUS7_SEL": 0x2f,

    "RTC0_RTC_CLK_TEST_SEL": 0x30,

    "SPI1_SPICLK_SEL": 0x31,
    "SPI1_SPICSB_SEL": 0x32,
    "SPI1_SPIMISO_SEL": 0x33,
    "SPI1_SPIMOSI_SEL": 0x34,

    "SPS0_TESTBUS0_SEL": 0x35,
    "SPS0_TESTBUS1_SEL": 0x36,
    "SPS0_TESTBUS2_SEL": 0x37,
    "SPS0_TESTBUS3_SEL": 0x38,
    "SPS0_TESTBUS4_SEL": 0x39,
    "SPS0_TESTBUS5_SEL": 0x3a,
    "SPS0_TESTBUS6_SEL": 0x3b,
    "SPS0_TESTBUS7_SEL": 0x3c,

    "TEMP0_TST_ADC_CLK_SEL": 0x3d,
    "TEMP0_TST_ADC_HI_SER_SEL": 0x3e,
    "TEMP0_TST_ADC_LO_SER_SEL": 0x3f,
    "TEMP0_TST_ADC_VLD_SER_SEL": 0x40,
    "TRNG0_TRNG_RO_DIV_SEL": 0x41,
    "TRNG0_TRNG_RO_REF_DIV_SEL": 0x42,

    "UART0_CTS_SEL": 0x43,
    "UART0_RTS_SEL": 0x44,
    "UART0_RX_SEL": 0x45,
    "UART0_TX_SEL": 0x46,

    "UART1_CTS_SEL": 0x47,
    "UART1_RTS_SEL": 0x48,
    "UART1_RX_SEL": 0x49,
    "UART1_TX_SEL": 0x4a,

    "UART2_CTS_SEL": 0x4b,
    "UART2_RTS_SEL": 0x4c,
    "UART2_RX_SEL": 0x4d,
    "UART2_TX_SEL": 0x4e,

    "USB0_EXT_DM_PULLUP_EN_SEL": 0x4f,
    "USB0_EXT_DP_RPU1_ENB_SEL": 0x50,
    "USB0_EXT_DP_RPU2_ENB_SEL": 0x51,
    "USB0_EXT_FS_EDGE_SEL_SEL": 0x52,
    "USB0_EXT_RX_DMI_SEL": 0x53,
    "USB0_EXT_RX_DPI_SEL": 0x54,
    "USB0_EXT_RX_RCV_SEL": 0x55,
    "USB0_EXT_SUSPENDB_SEL": 0x56,
    "USB0_EXT_TX_DMO_SEL": 0x57,
    "USB0_EXT_TX_DPO_SEL": 0x58,
    "USB0_EXT_TX_OEB_SEL": 0x59,

    "VOLT0_TST_NEG_GLITCH_DET_SEL": 0x5a,
    "VOLT0_TST_POS_GLITCH_DET_SEL": 0x5b,

    "XO0_TESTBUS0_SEL": 0x5c,
    "XO0_TESTBUS1_SEL": 0x5d,
    "XO0_TESTBUS2_SEL": 0x5e,
    "XO0_TESTBUS3_SEL": 0x5f,
    "XO0_TESTBUS4_SEL": 0x60,
    "XO0_TESTBUS5_SEL": 0x61,
    "XO0_TESTBUS6_SEL": 0x62,
    "XO0_TESTBUS7_SEL": 0x63,
}

PINMUX_CTL_REGS = {
    # These have both SEL + CTL registers, in [SEL | CTL] order
    "DIOM_CTL": reg_list(0x4, 5, 8),
    "DIOA_CTL": reg_list(0x2c, 15, 8),
    "DIOB_CTL": reg_list(0xa4, 8, 8),
    "RESETB_CTL": 0xe4,
    "VIO_CTL": reg_list(0xec, 2, 8),
}

PINMUX_REGS = { # Other PINMUX regs
    "EXITEN0": 0x284,
    "EXITEDGE0": 0x288,
    "EXITINV0": 0x28c,
    "HOLD": 0x290,
}

PINMUX_SEL_REGS_LIST = []
for v in PINMUX_SEL_REGS.values():
    if type(v) == list:
        for i in v:
            PINMUX_SEL_REGS_LIST.append(i)
    elif type(v) == int:
        PINMUX_SEL_REGS_LIST.append(v)

PINMUX_CTL_REGS_LIST = []
for v in PINMUX_CTL_REGS.values():
    if type(v) == list:
        for i in v:
            PINMUX_CTL_REGS_LIST.append(i)
    elif type(v) == int:
        PINMUX_CTL_REGS_LIST.append(v)