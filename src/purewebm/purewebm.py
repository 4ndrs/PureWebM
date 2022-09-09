# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Utility to encode quick webms with ffmpeg"""

import sys
import os
from types import SimpleNamespace

from . import webm as wbm
from . import CONFIG_PATH


def enqueue(queue, kwargs):
    """Appends the encoding information to the queue"""
    webm = SimpleNamespace()
    webm = wbm.prepare(webm, kwargs)

    queue.items.append(webm)
    queue.total_size.set(queue.total_size.get() + 1)


def verify_config():
    """Checks the configuration folder, creates it if it doesn't exist"""
    if not CONFIG_PATH.exists():
        try:
            CONFIG_PATH.mkdir(parents=True)
        except PermissionError:
            print(
                "Unable to create the configuration folder "
                f"{CONFIG_PATH}, permission denied",
                file=sys.stderr,
            )
            sys.exit(os.EX_CANTCREAT)
