# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Utility to encode quick webms with ffmpeg.

For usage instructions run: purewebm -h"""

import importlib.metadata
import pathlib

__version__ = importlib.metadata.version(__package__)
CONFIG_PATH = pathlib.Path("~/.config/PureWebM").expanduser()
