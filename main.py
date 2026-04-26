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
import fcntl
import select
import argparse
import sys
import signal
import termios

from lib.logger import GscemuLogger
from env import *
from src.haven import Emulator as havnEmulator

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

def stdout_emu_char_write_pts_callback(char: int, unused):
    try:    
        sys.stdout.write(chr(char))
        sys.stdout.flush()
    except Exception as e:
        print(f"pty emu -> user error: {e}")

def stdout_user_char_write_emu_thread(call_fn):
    while True:
        try:
            char = sys.stdin.read(1)
            if char == '\x03': # Ctrl+C
                signal.raise_signal(signal.SIGINT)
            elif char == '\x13': # Ctrl+S
                signal.raise_signal(signal.SIGUSR1)
            else:
                call_fn(ord(char))
        except Exception as e:
            prints.error(f"pty user -> emu error: {e}")
            break

def pts_emu_char_write_pts_callback(char: int, master_fd):
    try:    
        os.write(master_fd, bytes([char]))
    except Exception as e:
        print(f"pty emu -> user error: {e}")

def pts_user_char_write_emu_thread(call_fn, master_fd):
    while True:
        try:
            # Wait until we recieve data, since O_NONBLOCK is enabled now.
            select.select([master_fd], [], [])

            call_fn(ord(os.read(master_fd, 1)))
        except Exception as e:
            prints.error(f"pty user -> emu error: {e}")
            break

def setup_uart_output_method(chipemu: havnEmulator, output_method: str):
    if output_method == "pts":
        master_fd, slave_fd = pty.openpty()
        tty.setraw(master_fd)
        tty.setraw(slave_fd)

        slave_name = os.ttyname(slave_fd)

        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        write_thread = threading.Thread(
            target=pts_user_char_write_emu_thread, 
            daemon=True,
            args=(chipemu.uart_input, master_fd)
        )
        write_thread.start()

        chipemu.set_uart_output_fn(
            pts_emu_char_write_pts_callback,
            master_fd
        )

        print(f"Emulator UART0: {slave_name}")

    elif output_method == "stdout":
        # for macOS to ensure ctrl+s is detected.
        new_settings = termios.tcgetattr(sys.stdin)
        new_settings[0] &= ~termios.IXON
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, new_settings)

        tty.setcbreak(sys.stdin.fileno())

        write_thread = threading.Thread(
            target=stdout_user_char_write_emu_thread, 
            daemon=True,
            args=(chipemu.uart_input,)
        )
        write_thread.start()

        chipemu.set_uart_output_fn(
            stdout_emu_char_write_pts_callback
        )

    else:
        print("setup_uart_output_method recieved an invalid output method!")

def main():
    _argparser = argparse.ArgumentParser(
        prog="gscemu",
        description="An emulator for the Google Security Chip(s), " \
        "whereby the stock firmware can be run. All components are " \
        "intended to match the original behavior of the silicon " \
        "as much as possible."
    )

    _argparser.add_argument(
        "-o", "--console-output", default="stdout", choices=["stdout", "pts"],
        help="Where to print the UART output to, " \
        "and where to recieve input from."
    )
    _argparser.add_argument(
        "-w", "--wait-for-enter", action='store_true',
        help="Wait for user to press 'Enter' to start emulation"
    )

    args = _argparser.parse_args()

    chipemu = havnEmulator(
        GSCEMULATOR_FW_PATHS,
        GSCEMULATOR_FW_STRICT_SIZE_CHECKING
    )

    setup_uart_output_method(chipemu, args.console_output)

    if args.wait_for_enter:
        input("Emulator setup complete! Press Enter to start emulaton...")
        print("Emulation started!")

    chipemu.start_emulation()

# We need this now that we're making gscemu a pip installable CLI tool, so that
# we do not double call the main function, causing double emulator
# initialization and more issues down the line.
# gscemu should also still be runnable from python3 main.py, thus we still
# keep this.
if __name__ == "__main__":
    main()