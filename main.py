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

import termios
import sys
import signal
import threading
import tty

from lib.logger import GscemuLogger
from env import *
from src.haven import Emulator as havnEmulator

old_terminal_settings = termios.tcgetattr(sys.stdin)
prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

def char_handler_worker(recieve_fn):
    while True:
        char = sys.stdin.read(1)
        if char == '\x03': # Ctrl+C
            signal.raise_signal(signal.SIGINT)
        elif char == '\x13': # Ctrl+S
            signal.raise_signal(signal.SIGUSR1)
        else:
            recieve_fn(ord(char))

# TODO(appleflyer): implement arg system
def main():
    chipemu = havnEmulator(
        GSCEMULATOR_FW_PATHS,
        GSCEMULATOR_FW_STRICT_SIZE_CHECKING
    )

    # for macOS to ensure ctrl+s is detected.
    new_settings = termios.tcgetattr(sys.stdin)
    new_settings[0] &= ~termios.IXON
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, new_settings)

    tty.setcbreak(sys.stdin.fileno())
    char_recieve_thread = threading.Thread(
        target=char_handler_worker, daemon=True, args=(chipemu.uart_input,)
    )
    char_recieve_thread.start()

    chipemu.start_emulation()

main()