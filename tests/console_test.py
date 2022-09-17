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
