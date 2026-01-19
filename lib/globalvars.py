# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import unicorn as qemu

from lib.threadutils import UcMutex
from env import GSCEMULATOR_LOGGER_SETTINGS
from lib.logger import GscemuLogger

THUMB_BIT = 1
DEFAULT_REG_WITDH = 0x10000 # Standard across all GSC variants

UNICORN_MEM_INVALID_HOOKS = (qemu.UC_HOOK_MEM_READ_UNMAPPED |
                             qemu.UC_HOOK_MEM_WRITE_UNMAPPED |
                             qemu.UC_HOOK_MEM_FETCH_UNMAPPED)

# It is important that these variables are assigned to an object
# before they are used. If the developer calls the ucmutex function without
# initializing the variable, it is simply developer negligence and we should
# not sacrifice performance by checking everytime if the ucmutex_raw variable
# has a value.
ucmutex_raw = None

# Interesting design choice I made here, but let's try and standardize
# a global uc object too, not messily depend on the object being passed
# through hooks and so on.
g_uc_raw = None

def g_uc() -> qemu.Uc:
    return g_uc_raw

def ucmutex() -> UcMutex:
    return ucmutex_raw

def assign_global_uc(uc: qemu.Uc) -> None:
    global ucmutex_raw, g_uc_raw
    
    if not g_uc_raw:
        g_uc_raw = uc

    if not ucmutex_raw:
        ucmutex_raw = UcMutex(uc)