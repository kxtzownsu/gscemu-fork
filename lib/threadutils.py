# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

import unicorn as qemu
import threading
import collections

class FifoLock:
    """FIFO(first in, first out) oriented threading.Lock.

    This class is to ensure that threads which attempt to get hold of a 
    singular lock get access to the lock in priority. Of course, on a
    nanosecond scale, this is still non-deterministic, and that cannot be fixed.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._waiters = collections.deque()
    
    def acquire(self):
        cv = threading.Condition(self._lock)
        
        with self._lock:
            self._waiters.append(cv)
            
            while len(self._waiters) > 0 and self._waiters[0] is not cv:
                cv.wait()
    
    def release(self):
        with self._lock:
            if self._waiters:
                self._waiters.popleft()
            
            if self._waiters:
                self._waiters[0].notify()

    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False

class UcMutex:
    """Implements a mutex system for unicorn engine operations.

    This is to ensure thread safety for objects within the unicorn engine.
    By default, unicorn does not guarantee thread safety for 
    reg_write/reg_read/mem_write/mem_read. We need to implement this
    ourself.
    """

    def __init__(self, uc: qemu.Uc):
        self.uc = uc
        self.mutex = FifoLock()

    def reg_read(self, *args, **kwargs):
        with self.mutex:
            return self.uc.reg_read(*args, **kwargs)

    def reg_write(self, *args, **kwargs):
        with self.mutex:
            return self.uc.reg_write(*args, **kwargs)

    def mem_read(self, *args, **kwargs):
        with self.mutex:
            return self.uc.mem_read(*args, **kwargs)

    def mem_write(self, *args, **kwargs):
        with self.mutex:
            return self.uc.mem_write(*args, **kwargs)
        
    # Non-standard helpers.

    def int32_mem_read(self, address):
        with self.mutex:
            return int.from_bytes(self.uc.mem_read(address, 4), 'little')

    def int32_mem_write(self, address, val):
        with self.mutex:
            return self.uc.mem_write(address, int.to_bytes(val, 4, 'little'))
        
    def int16_mem_read(self, address):
        with self.mutex:
            return int.from_bytes(self.uc.mem_read(address, 2), 'little')