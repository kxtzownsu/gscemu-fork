# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

"""
Class to keep emulator context state, to pass around objects of classes made
necessary for multi-threaded emulator opeeration.. This makes gscemulator
more modular instead of being restrictive about module paths, and only being
able to create one Emulator object.
"""

# Needed for type hints
import unicorn as qemu
from lib.ucthread import UcThread
from lib.threadutils import UcMutex


class ComponentObjects:
    def __init__(self, object=None, read_fn=None, write_fn=None):
        self.object = object
        self.read_fn = read_fn
        self.write_fn = write_fn


class EmulatorContext:
    def __init__(self, uc: qemu.Uc = None):
        if uc is None:
            raise ValueError("uc cannot be empty!")

        self.uc: qemu.Uc = uc

        self.ucmutex: UcMutex = UcMutex(self.uc)
        self.ucthread: UcThread = UcThread(self.uc)

        # Follow a standard of
        # {
        #   "GPIO": ComponentObjects,
        #   "GLOBALSEC": ComponentObjects,
        # }
        # E.g. can be accessed as ctx.components["GPIO"].read_fn
        self.components: dict[str, ComponentObjects] = {}

        # Pointer to components for fast lookup.
        self.c_fast = None
