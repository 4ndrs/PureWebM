# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Module for handling the interprocess communication"""

import os
import pathlib
import logging
from types import SimpleNamespace
from multiprocessing.connection import Listener, Client

from . import CONFIG_PATH


def listen(queue, socket, kill_event):
    """Listens for connections using the specified socket, enqueues the data
    received in the queue, and sends the queue's information if requested"""
    socket = str(socket)
    key = get_key()
    with Listener(socket, "AF_UNIX", authkey=key) as listener:
        logging.info("Listening for connections on %s", socket)
        try:
            while True:
                with listener.accept() as conn:
                    data = conn.recv()
                    if isinstance(data, str):
                        if "get-queue" in data:
                            logging.info(
                                "get-queue request received, sending the "
                                "current queue's information"
                            )
                            tmp_queue = SimpleNamespace()
                            tmp_queue.status = queue.status.get()
                            tmp_queue.encoding = queue.encoding.get()
                            tmp_queue.total_size = queue.total_size.get()
                            conn.send(tmp_queue)
                        elif "kill" in data:
                            logging.info(
                                "kill request received, setting the "
                                "kill_event and stopping the listener"
                            )
                            kill_event.set()
                            break
                    else:
                        logging.info(
                            "Received new encoding parameters, adding to the "
                            "queue"
                        )
                        queue.items.append(data)
                        queue.total_size.set(queue.total_size.get() + 1)
        except KeyboardInterrupt:
            pass  # The keyboard interrupt message is handled by main()


def send(data, socket):
    """Sends the data using the specified socket"""
    socket = str(socket)
    key = get_key()
    with Client(socket, "AF_UNIX", authkey=key) as conn:
        conn.send(data)


def get_queue(socket):
    """Gets the current queue information from the main process"""
    socket = str(socket)
    key = get_key()
    with Client(socket, "AF_UNIX", authkey=key) as conn:
        conn.send("get-queue")
        queue = conn.recv()
    return queue


def get_key():
    """Returns the key for IPC, read from a key file, generates it if it
    doesn't exists"""
    key_file = CONFIG_PATH / pathlib.Path("PureWebM.key")

    if key_file.exists() and key_file.stat().st_size > 0:
        with open(key_file, "rb") as file:
            key = file.read()
        return key

    # Generate the file and the key with os.urandom()
    # The file will be masked with 600 permissions
    logging.warning(
        "The key file %s does not exist, generating a new one", key_file
    )
    key = os.urandom(256)
    file_descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT, 0o600)
    with open(file_descriptor, "wb") as file:
        file.write(key)
    return key
