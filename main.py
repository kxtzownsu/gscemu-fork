# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

"""Wrapper file to interact with the gscemu emulator object. 

Of course, this project is already modular so others can integrate it into their
other projects, if needed. But this wrapper file allows a developer to start an
instance of gscemulator independently, for testing or fuzzing, so that they need
not to take the effort to create code to interact with the emulator object.

This main.py file was built for the haven Emulator object, but we will add more
support in the future.
"""

import os
import threading
import tty
import pty

from lib.logger import GscemuLogger
from env import *
from src.haven import Emulator as havnEmulator

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

def emu_char_write_pts_callback(char: int, master_fd):
    os.write(master_fd, bytes([char]))

def user_char_write_emu_thread(call_fn, master_fd):
    while True:
        try:
            call_fn(ord(os.read(master_fd, 1)))
        except Exception as e:
            print(e)

def setup_pts_device(chipemu: havnEmulator):
    master_fd, slave_fd = pty.openpty()
    tty.setraw(slave_fd)

    slave_name = os.ttyname(slave_fd)

    write_thread = threading.Thread(
        target=user_char_write_emu_thread, 
        daemon=True,
        args=(chipemu.uart_input, master_fd)
    )
    write_thread.start()

    chipemu.set_uart_output_fn(
        emu_char_write_pts_callback,
        master_fd
    )

    print(f"Emulator UART0 at {slave_name}")

# TODO(appleflyer): implement arg system
def main():
    chipemu = havnEmulator(
        GSCEMULATOR_FW_PATHS,
        GSCEMULATOR_FW_STRICT_SIZE_CHECKING
    )

    setup_pts_device(chipemu)

    chipemu.start_emulation()

# We need this now that we're making gscemu a pip installable CLI tool, so that
# we do not double call the main function, causing double emulator
# initialization and more issues down the line.
# gscemu should also still be runnable from python3 main.py, thus we still
# keep this.
if __name__ == "__main__":
    main()