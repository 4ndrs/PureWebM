# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
from types import SimpleNamespace
from multiprocessing import Manager

from purewebm import console

CLEAR_LINE = "\r\033[K"
COLOR = SimpleNamespace(
    green="\033[1;92m",
    blue="\033[1;94m",
    red="\033[1;91m",
    endc="\033[0m",
)


def test_print_encoding(capsys):
    value = Manager().Value(int, 5)
    console._print_encoding(1, value)
    captured = capsys.readouterr()
    assert captured.out == f"{CLEAR_LINE}Encoding 1 of 5: "


def test_print_progress_blue(capsys):
    total_size = Manager().Value(int, 3)
    console.print_progress("Processing", 2, total_size, color="blue")
    captured = capsys.readouterr()
    assert (
        captured.out == f"{CLEAR_LINE}Encoding 2 of 3: "
        f"{COLOR.blue}Processing{COLOR.endc}"
    )


def test_print_progress_green(capsys):
    total_size = Manager().Value(int, 2)
    console.print_progress("Done", 2, total_size, color="green")
    captured = capsys.readouterr()
    assert (
        captured.out == f"{CLEAR_LINE}Encoding 2 of 2: "
        f"{COLOR.green}Done{COLOR.endc}"
    )


def test_print_progress_invalid(capsys):
    total_size = Manager().Value(int, 1)
    console.print_progress("Processing", 1, total_size, color="invalid")
    captured = capsys.readouterr()
    assert captured.out == f"{CLEAR_LINE}Encoding 1 of 1: "
    assert captured.err == f"{COLOR.red}Unimplemented color: invalid\n"
