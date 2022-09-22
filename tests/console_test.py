# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
from types import SimpleNamespace

from purewebm import console

CLEAR_LINE = "\r\033[K"
COLOR = SimpleNamespace(
    green="\033[1;92m",
    blue="\033[1;94m",
    red="\033[1;91m",
    endc="\033[0m",
)


def test_print_encoding(capsys):
    total_size = 5
    console._print_encoding(1, total_size)
    captured = capsys.readouterr()
    assert captured.out == f"{CLEAR_LINE}Encoding 1 of 5: "


def test_print_progress_blue(capsys):
    total_size = 3
    console.print_progress("Processing", 2, total_size, color="blue")
    captured = capsys.readouterr()
    assert (
        captured.out == f"{CLEAR_LINE}Encoding 2 of 3: "
        f"{COLOR.blue}Processing{COLOR.endc}"
    )


def test_print_progress_green(capsys):
    total_size = 2
    console.print_progress("Done", 2, total_size, color="green")
    captured = capsys.readouterr()
    assert (
        captured.out == f"{CLEAR_LINE}Encoding 2 of 2: "
        f"{COLOR.green}Done{COLOR.endc}"
    )


def test_print_progress_invalid(capsys):
    total_size = 1
    console.print_progress("Processing", 1, total_size, color="invalid")
    captured = capsys.readouterr()
    assert captured.out == f"{CLEAR_LINE}Encoding 1 of 1: "
    assert captured.err == f"{COLOR.red}Unimplemented color: invalid\n"


def test_print_progress_zero_total_size(capsys):
    total_size = 0
    console.print_progress("Checking fonts", 0, total_size, color=None)
    captured = capsys.readouterr()
    assert captured.out == "Checking fonts\n"


def test_print_error_defaults(capsys):
    total_size = 1
    console.print_error("second pass", 1, total_size)
    captured = capsys.readouterr()
    assert captured.out == f"{CLEAR_LINE}Encoding 1 of 1: "
    assert (
        captured.err
        == f"{COLOR.red}Error encountered during the execution of the "
        f"second pass\n{COLOR.endc}"
    )


def test_print_error_cmdoutput(capsys):
    total_size = 1
    console.print_error(
        "second pass",
        1,
        total_size,
        cmd="test_cmd -v",
        output="Error message",
    )
    captured = capsys.readouterr()
    assert captured.out == f"{CLEAR_LINE}Encoding 1 of 1: "
    assert (
        captured.err
        == f"{COLOR.red}Error encountered during the execution of the "
        "second pass\n"
        "Command: test_cmd -v\n"
        f"Output: Error message{COLOR.endc}"
    )
