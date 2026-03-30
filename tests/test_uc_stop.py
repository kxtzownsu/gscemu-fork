# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

"""File that proves uc_emu_stop behavior.

On a uc_emu_stop behavior, the emulation stops on the next TB. It was not clear
whether the pc was advanced to the next instruction but hasn't been executed
yet.

This file shows that the PC is advanced to the next instruction that the
emulator plans to execute, but the instruction is not actually executed yet.
"""

import unicorn as emu
import threading
import time
with open('/Users/appleflyer/titanm/arm-code-assembler/code.bin', 'rb') as f:
    code = f.read()

# assembly used:
# .global _start
# _start:
# 1:
#     add r0, r0, #1
#     mov r1, r0
#     mov r2, r0
#     mov r3, r0
#     mov r4, r0
#     mov r5, r0
#     mov r6, r0
#     mov r7, r0
#     mov r8, r0
#     mov r9, r0
#     mov r10, r0
#     b 1b

uc = emu.Uc(emu.UC_ARCH_ARM, emu.UC_MODE_THUMB, emu.arm_const.UC_CPU_ARM_CORTEX_M3)
uc.mem_map(0x0, 0x1000)
uc.mem_write(0x0, code)

stage2 = threading.Event()

regs = [
    emu.arm_const.UC_ARM_REG_R0,
    emu.arm_const.UC_ARM_REG_R1,
    emu.arm_const.UC_ARM_REG_R2,
    emu.arm_const.UC_ARM_REG_R3,
    emu.arm_const.UC_ARM_REG_R4,
    emu.arm_const.UC_ARM_REG_R5,
    emu.arm_const.UC_ARM_REG_R6,
    emu.arm_const.UC_ARM_REG_R7,
    emu.arm_const.UC_ARM_REG_R8,
    emu.arm_const.UC_ARM_REG_R9,
    emu.arm_const.UC_ARM_REG_R10,

]

def wait_thread():
    global uc

    time.sleep(0.001)
    uc.emu_stop()

    for reg in regs:
        print(uc.reg_read(reg))
    print(uc.reg_read(emu.arm_const.UC_ARM_REG_PC))
    
    stage2.set()

    time.sleep(0.001)
    uc.emu_stop()

    for reg in regs:
        print(uc.reg_read(reg))
    print(uc.reg_read(emu.arm_const.UC_ARM_REG_PC))

    return

thread_stop = threading.Thread(target=wait_thread)
thread_stop.start()

uc.emu_start(0x0|1, 0xFFFFFFFF)
stage2.wait()
uc.emu_start(uc.reg_read(emu.arm_const.UC_ARM_REG_PC)|1, 0xFFFFFFFF)

# output

# 614480
# 614480
# 614480
# 614480
# 614480
# 614480
# 614480
# 614480
# 614480
# 614480
# 614480
# 0
# 1197151
# 1197151
# 1197151
# 1197151
# 1197151
# 1197151
# 1197151
# 1197151
# 1197151
# 1197151
# 1197151
# 0