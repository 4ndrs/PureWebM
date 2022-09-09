# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Utility to encode quick webms with ffmpeg"""

import sys
import os
import pathlib
from types import SimpleNamespace
from multiprocessing.connection import Listener, Client

from . import webm as wbm
from . import CONFIG_PATH


def enqueue(queue, kwargs):
    """Appends the encoding information to the queue"""
    webm = SimpleNamespace()
    webm = wbm.prepare(webm, kwargs)

    queue.items.append(webm)
    queue.total_size.set(queue.total_size.get() + 1)


def listen(queue, socket):
    """Listen for connections for interprocess communication using
    Unix sockets, sends the received kwargs to enqueue"""
    socket = str(socket)
    key = get_key()
    with Listener(socket, "AF_UNIX", authkey=key) as listener:
        try:
            while True:
                with listener.accept() as conn:
                    kwargs = conn.recv()
                    enqueue(queue, kwargs)
        except KeyboardInterrupt:
            pass  # The keyboard interrupt message is handled by main()


def send(kwargs, socket):
    """Attempts to connect to the Unix socket, and sends the kwargs to the
    main process if successful"""
    socket = str(socket)
    key = get_key()
    with Client(socket, "AF_UNIX", authkey=key) as conn:
        conn.send(kwargs)


def get_key():
    """Returns the key for IPC, read from a key file, generates it if it doesn't
    exists"""
    key_file = CONFIG_PATH / pathlib.Path("PureWebM.key")

    if key_file.exists() and key_file.stat().st_size > 0:
        with open(key_file, "rb") as file:
            key = file.read()
        return key

    # Generate the file and the key with os.urandom()
    # The file will be masked with 600 permissions
    key = os.urandom(256)
    file_descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT, 0o600)
    with open(file_descriptor, "wb") as file:
        file.write(key)
    return key


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
