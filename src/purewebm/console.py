# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Module for printing stuff to the console"""


def print_progress(message, progress, total_size):
    """Prints the encoding progress with a customized message"""
    clear_line = "\r\033[K"
    print(
        f"{clear_line}Encoding {progress} of {total_size.get()}: {message}",
        end="",
        flush=True,
    )
