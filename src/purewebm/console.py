# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Module for printing stuff to the console"""

import sys
from types import SimpleNamespace

CLEAR_LINE = "\r\033[K"
COLOR = SimpleNamespace(
    green="\033[1;92m",
    blue="\033[1;94m",
    red="\033[1;91m",
    endc="\033[0m",
)


def print_progress(
    message, encoding, total_size, color="blue", no_clear=False
):
    """Prints the encoding progress with a customized message"""

    if total_size > 0:
        _print_encoding(encoding, total_size, no_clear)

    if color == "red":
        print(f"{COLOR.red}{message}", end=f"{COLOR.endc}", flush=True)
    elif color == "green":
        print(f"{COLOR.green}{message}", end=f"{COLOR.endc}", flush=True)
    elif color == "blue":
        print(f"{COLOR.blue}{message}", end=f"{COLOR.endc}", flush=True)
    elif color is None:
        print(message, end="", flush=True)
    else:
        print(f"{COLOR.red}Unimplemented color: {color}", file=sys.stderr)

    if total_size < 1:
        print(end="\n")


def print_error(where, encoding, total_size, cmd=None, output=None):
    """prints the progress with an error message"""

    _print_encoding(encoding, total_size)

    message = f"Error encountered during the execution of the {where}\n"
    message += f"Command: {cmd}\n" if cmd else ""
    message += f"Output: {output}" if output else ""

    print(
        f"{COLOR.red}{message}",
        end=f"{COLOR.endc}",
        file=sys.stderr,
        flush=True,
    )


def _print_encoding(encoding, total_size, no_clear=False):
    if no_clear:
        print(
            f"Encoding {encoding} of {total_size}: ",
            end="",
        )
    else:
        print(
            f"{CLEAR_LINE}Encoding {encoding} of {total_size}: ",
            end="",
        )
