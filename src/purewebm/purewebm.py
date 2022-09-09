# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Utility to encode quick webms with ffmpeg"""

import sys
import os
import re
import pathlib
import hashlib
from types import SimpleNamespace
from multiprocessing.connection import Listener, Client

from . import CONFIG_PATH
from .ffmpeg import get_duration


def enqueue(queue, kwargs):
    """Appends the encoding information to the queue"""
    webm = SimpleNamespace()
    webm = prepare(webm, kwargs)

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


def prepare(webm, kwargs):
    """Prepares the webm namespace"""
    webm.inputs = kwargs["input"]
    webm.output = kwargs["output"]
    webm.encoder = kwargs["encoder"]
    webm.crf = kwargs["crf"]
    webm.size_limit = kwargs["size_limit"]
    webm.lavfi = kwargs["lavfi"]
    webm.ss = kwargs["start_time"]
    webm.to = kwargs["stop_time"]
    webm.extra_params = kwargs["extra_params"]

    webm.two_pass = True
    webm.input_seeking = True
    webm.params = (
        "-map_metadata -1 -map_chapters -1 -map 0:v -f webm -row-mt 1 -speed 0"
    )

    if webm.extra_params:
        if "-c:v" in webm.extra_params:
            encoder = re.search(r"-c:v\s+(\w+)", webm.extra_params)
            webm.encoder = encoder if encoder else webm.encoder
        if "-crf" in webm.extra_params:
            crf = re.search(r"-crf\s+(\d+)", webm.extra_params)
            crf = crf if crf else webm.crf

    # To sync the burned subtitles need output seeking
    if webm.lavfi and "subtitle" in webm.lavfi:
        webm.input_seeking = False

    if "libvpx" not in webm.encoder:
        webm.two_pass = False
        webm.input_seeking = False
        webm.params = "-f matroska -map 0 -c copy -preset veryslow"

    start, stop = get_duration(webm.inputs[0])
    if None in (start, stop):
        print(
            "An unexpected error occurred whilst retrieving "
            f"the metadata for the input file {webm.inputs[0].absolute()}",
            file=sys.stderr,
        )
        sys.exit(os.EX_SOFTWARE)

    webm.ss = start if webm.ss is None else webm.ss
    webm.to = stop if webm.to is None else webm.to

    if webm.output is None:
        if "http" in str(webm.inputs[0]):
            input_filename = "http_vid"
        else:
            input_filename = webm.inputs[0].absolute().stem
        webm.output = generate_filename(
            webm.ss,
            webm.to,
            webm.extra_params,
            encoder=webm.encoder,
            input_filename=input_filename,
            save_path=pathlib.Path("~/Videos/PureWebM").expanduser(),
        )

    if not webm.output.parent.exists():
        try:
            webm.output.parent.mkdir(parents=True)
        except PermissionError:
            print(
                f"Unable to create folder {webm.output.parent}, "
                "permission denied.",
                file=sys.stderr,
            )
            sys.exit(os.EX_CANTCREAT)

    return webm


def generate_filename(*seeds, encoder, input_filename, save_path):
    """Generates the filename for the output file using an MD5 hash of the seed
    variables and the name of the input file"""
    md5 = hashlib.new("md5", usedforsecurity=False)
    for seed in seeds:
        md5.update(str(seed).encode())

    extension = ".webm" if "libvpx" in encoder else ".mkv"
    filename = input_filename + "_" + md5.hexdigest()[:10] + extension

    return save_path / filename


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


def get_seconds(timestamp):
    """Converts timestamp to seconds with 3 decimal places"""
    seconds = sum(
        (
            float(num) * (60**index)
            for index, num in enumerate(reversed(timestamp.split(":")))
        )
    )

    return round(seconds, 3)


def print_progress(message, progress, total_size):
    """Prints the encoding progress with a customized message"""
    clear_line = "\r\033[K"
    print(
        f"{clear_line}Encoding {progress} of {total_size.get()}: {message}",
        end="",
        flush=True,
    )


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
