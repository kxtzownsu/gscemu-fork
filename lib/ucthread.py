# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

import threading
import unicorn as qemu
import time

class UcThread:
    def __init__(self, uc: qemu.Uc):
        self.uc = uc
        
        self.emu_thread = None
        self.stop_lock = threading.Event() # set = unpause, clear = pause
        
        self.exit_thread_signal = threading.Event()

    def emu_thread_worker(self):
        while True:
            # Wait until the stop lock event is cleared.
            self.stop_lock.wait(None)

            if self.exit_thread_signal.is_set():
                # appleflyer: Should we add a delay for other components to
                # have sufficient time to clean up?
                return

            # TODO(appleflyer): Change this to uc.emu_run when pr is merged into 
            # 2.1.5-dev.
            self.uc.emu_start(
                self.uc.reg_read(qemu.arm_const.UC_ARM_REG_PC) | 1, 
                0xFFFFFFFF
            )

    def emu_start(self) -> bool:
        if not self.emu_thread:
            # stop_lock and exit_thread_signal should not have been set yet.
            self.emu_thread = threading.Thread(target=self.emu_thread_worker)
            self.emu_thread.daemon = False
            self.stop_lock.set()
            self.emu_thread.start()
        else:
            # Looks like the thread is paused. Unpause it.
            self.stop_lock.set()

        return True

    def emu_pause(self) -> bool:
        if not self.emu_thread:
            return False
        
        try:
            self.stop_lock.clear()
            self.uc.emu_stop()
            return True
        except:
            return False

    def emu_halt(self) -> bool:
        if not self.emu_thread:
            return False
        
        try:
            self.stop_lock.set()
            self.exit_thread_signal.set()
            self.uc.emu_stop()
            return True
        except:
            return False