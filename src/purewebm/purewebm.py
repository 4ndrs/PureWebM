#!/usr/bin/env python3
# Copyright (c) 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Utility to encode quick webms with ffmpeg"""

import sys
import os
import re
import time
import pathlib
import hashlib
import subprocess  # nosec
from types import SimpleNamespace
from multiprocessing import Process, Event, Manager
from multiprocessing.connection import Listener, Client


def main():
    """Main function"""
    try:
        kwargs = dict(arg.split("=") for arg in sys.argv[1:])

    except ValueError:
        print("keyword arguments must be supplied", file=sys.stderr)
        print_usage()
        sys.exit(os.EX_USAGE)

    if "input" not in kwargs:
        print("An input file must be supplied to proceed", file=sys.stderr)
        print_usage()
        sys.exit(os.EX_USAGE)

    socket = pathlib.Path("PureWebM")

    if socket.exists():
        send(kwargs, socket)
        print("Encoding information sent to the main process")
        sys.exit(os.EX_OK)

    # Main process does not exist, starting a new queue
    manager = Manager()
    encoding_done = Event()

    queue = manager.list()
    enqueue(queue, kwargs)

    listen_process = Process(target=listen, args=(queue, socket))
    encode_process = Process(target=encode, args=(queue, encoding_done))
    listen_process.start()
    encode_process.start()

    while True:
        if encoding_done.is_set():
            listen_process.terminate()
            socket.unlink()
            sys.exit(os.EX_OK)

        time.sleep(1)


def enqueue(queue, kwargs):
    """Appends the encoding information to the queue"""
    webm = SimpleNamespace()
    webm = prepare(webm, kwargs)

    queue.append(webm)


def listen(queue, socket):
    """Listen for connections for interprocess communication using
    Unix sockets, sends the received kwargs to enqueue"""
    socket = str(socket)
    with Listener(socket, "AF_UNIX", authkey=b"secret password") as listener:
        while True:
            with listener.accept() as conn:
                kwargs = conn.recv()
                enqueue(queue, kwargs)


def send(kwargs, socket):
    """Attempts to connect to the Unix socket, and sends the kwargs to the
    main process if successful"""
    socket = str(socket)
    with Client(socket, "AF_UNIX", authkey=b"secret password") as conn:
        conn.send(kwargs)


def encode(queue, encoding_done):
    """Encodes the webms in the queue list"""

    size = len(queue)
    while queue:
        webm = queue.pop(0)
        if webm.twopass:
            first_pass, second_pass = generate_ffmpeg_args(webm)
        else:
            single_pass = generate_ffmpeg_args(webm)

        # First try with webm.crf and if the final file is bigger than
        # the webm.size_limit, then try again against a calculated bitrate
        # calc = (size_limit / real_duration * 8 * 1024 * 1024 / 1000)
        # if it fails again, calculate the difference in percentage and remove
        # it from the calculated bitrate, again and again until the file size
        # is equal to or lower than the size_limit

        # place holder
        print(
            f"Encoding {size - len(queue)} of {size}",
            flush=True,
            end="\r",
        )

        time.sleep(10)

        if len(queue) + 1 > size:
            size += len(queue)

    print("\nEncoding done")
    encoding_done.set()


def prepare(webm, kwargs):
    """Prepares the webm namespace"""
    webm.inputs = [pathlib.Path(path) for path in kwargs["input"].split(":+:")]

    # Set defaults
    webm.output = None
    webm.twopass = True
    webm.input_seeking = True
    webm.duration = None
    webm.params = (
        "-map_metadata -1 -map_chapters -1 -map 0:v -f webm -row-mt 1 -speed 0"
    )

    webm.encoder = kwargs.get("encoder", "libvpx-vp9")
    webm.crf = kwargs.get("crf", "24")
    webm.size_limit = kwargs.get("bitrate_limit", "3")  # In megabytes
    webm.lavfi = kwargs.get("lavfi", None)
    webm.ss = kwargs.get("ss", None)
    webm.to = kwargs.get("to", None)
    webm.extra_params = kwargs.get("extra_params", None)

    # To sync the burned subtitles need output seeking
    if webm.lavfi and "subtitle" in webm.lavfi:
        webm.input_seeking = False

    if webm.encoder == "libx264":  # Experimental
        webm.twopass = False
        webm.input_seeking = False
        webm.crf = "18" if "crf" not in kwargs else webm.crf
        webm.params = "-f matroska -map 0 -c copy -preset veryslow"

    start, duration = get_duration(webm.inputs[0])
    if duration is None:
        print(
            "An unexpected error occurred whilst retrieving "
            f"the metadata for the input file {webm.inputs[0].absolute()}",
            file=sys.stderr,
        )
        sys.exit(os.EX_SOFTWARE)

    if webm.ss is None:
        webm.ss = start
    if webm.to is None:
        webm.to = duration

    if "output" in kwargs:
        webm.output = pathlib.Path(kwargs["output"])
    else:
        webm.output = generate_filename(
            webm.ss,
            webm.to,
            webm.extra_params,
            encoder=webm.encoder,
            input_filename=webm.inputs[0].absolute().stem,
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


def generate_ffmpeg_args(webm):
    """Generates the ffmpeg args to pass to subprocess"""
    ffmpeg_args = []

    # if input seeking put the timestamps in front of the inputs
    if webm.input_seeking:
        for path in webm.inputs:
            ffmpeg_args += ["-ss", webm.ss, "-to", webm.to, "-i", path]
    else:
        for path in webm.inputs:
            ffmpeg_args += ["-i", path]
        ffmpeg_args += ["-ss", webm.ss, "-to", webm.to]

    ffmpeg_args += webm.params.split() + ["-c:v", webm.encoder]
    ffmpeg_args += ["-lavfi", webm.lavfi] if webm.lavfi else []
    ffmpeg_args += webm.extra_params.split() if webm.extra_params else []

    if webm.twopass:
        first_pass = ffmpeg_args + ["-pass", "1", "/dev/null", "-y"]
        second_pass = ffmpeg_args + ["-pass", "2", webm.output, "-y"]
        return first_pass, second_pass

    return ffmpeg_args + [webm.output, "-y"]


def generate_filename(*seeds, encoder, input_filename, save_path):
    """Generates the filename for the output file using an MD5 hash of the seed
    variables and the name of the input file"""

    md5 = hashlib.new("md5", usedforsecurity=False)
    for seed in seeds:
        md5.update(str(seed).encode())

    extension = ".webm" if "libvpx" in encoder else ".mkv"
    filename = input_filename + "_" + md5.hexdigest()[:10] + extension

    return save_path / filename


def get_duration(file_path):
    """Retrieves the file's duration and start times with ffmpeg"""

    pattern = (
        r"Duration:\s+(?P<duration>\d{2,}:\d{2}:\d{2}\.\d+),\s+"
        r"start:\s+(?P<start>\d+\.\d+)"
    )

    ffmpeg_output = subprocess.run(  # nosec
        ["ffmpeg", "-hide_banner", "-i", file_path],
        check=False,
        capture_output=True,
    ).stderr.decode()

    results = re.search(pattern, ffmpeg_output)

    if results is None:
        return None, None

    data = results.groupdict()

    return data["start"], data["duration"]


def print_usage(full=False):
    """Prints instructions"""

    if not full:
        print("Usage: -")


if __name__ == "__main__":
    main()
