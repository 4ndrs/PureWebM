# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Module for the handling of the configuration folder"""

import os
import sys
import shlex
import logging

from . import CONFIG_PATH


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


def load_config():
    """Loads the configuration file and returns the defaults"""
    crf = 24
    size_limit = 3
    deadline = "good"

    defaults = {"crf": crf, "size_limit": size_limit, "deadline": deadline}

    try:
        with open(f"{CONFIG_PATH}/PureWebM.conf", encoding="utf8") as file:
            data = file.read()
    except FileNotFoundError:
        return defaults

    options = shlex.split(data, comments=True)
    loaded_defaults = dict([option.split("=") for option in options])

    defaults["deadline"] = loaded_defaults.get("deadline", deadline)

    try:
        defaults["crf"] = int(loaded_defaults.get("crf", crf))
    except ValueError:
        logging.error(
            "Invalid value found in the configuration file for crf: %s",
            loaded_defaults["crf"],
        )
        logging.warning("Skipping invalid crf found in the configuration file")

    try:
        defaults["size_limit"] = int(
            loaded_defaults.get("size_limit", size_limit)
        )
    except ValueError:
        logging.error(
            "Invalid value found in the configuration file for size_limit: %s",
            loaded_defaults["size_limit"],
        )
        logging.warning(
            "Skipping invalid size_limit found in the configuration file"
        )

    return defaults
