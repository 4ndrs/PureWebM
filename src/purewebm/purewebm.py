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
import argparse
import subprocess  # nosec
from types import SimpleNamespace
from multiprocessing import Process, Event, Manager
from multiprocessing.connection import Listener, Client

from . import CONFIG_PATH, __version__


def main():
    """Main function"""

    kwargs = parse_argv()

    verify_config()
    socket = CONFIG_PATH / pathlib.Path("PureWebM.socket")

    if socket.exists():
        send(kwargs, socket)
        print("Encoding information sent to the main process")
        sys.exit(os.EX_OK)

    # Main process does not exist, starting a new queue
    manager = Manager()
    encoding_done = Event()

    queue = manager.Namespace()
    queue.items = manager.list()
    queue.total_size = 0
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

        time.sleep(0.2)


def enqueue(queue, kwargs):
    """Appends the encoding information to the queue"""
    webm = SimpleNamespace()
    webm = prepare(webm, kwargs)

    queue.items.append(webm)
    queue.total_size += 1


def listen(queue, socket):
    """Listen for connections for interprocess communication using
    Unix sockets, sends the received kwargs to enqueue"""
    socket = str(socket)
    key = get_key()
    with Listener(socket, "AF_UNIX", authkey=key) as listener:
        while True:
            with listener.accept() as conn:
                kwargs = conn.recv()
                enqueue(queue, kwargs)


def send(kwargs, socket):
    """Attempts to connect to the Unix socket, and sends the kwargs to the
    main process if successful"""
    socket = str(socket)
    key = get_key()
    with Client(socket, "AF_UNIX", authkey=key) as conn:
        conn.send(kwargs)


def encode(queue, encoding_done):
    """Encodes the webms in the queue list"""

    encoding = 0
    while queue.items:
        webm = queue.items.pop(0)
        encoding += 1
        if webm.twopass:
            first_pass, second_pass = generate_ffmpeg_args(webm)
        else:
            single_pass = generate_ffmpeg_args(webm)
            print(f"{single_pass}")

        # First try with webm.crf and if the final file is bigger than
        # the webm.size_limit, then try again against a calculated bitrate
        # calc = (size_limit / real_duration * 8 * 1024 * 1024 / 1000)
        # if it fails again, calculate the difference in percentage and remove
        # it from the calculated bitrate, again and again until the file size
        # is equal to or lower than the size_limit

        # place holder
        # print(
        #    f"Encoding {encoding} of {queue.total_size}",
        #    flush=True,
        #    end="\r",
        # )

        time.sleep(10)

    print("\nEncoding done")
    encoding_done.set()


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

    webm.twopass = True
    webm.input_seeking = True
    webm.params = (
        "-map_metadata -1 -map_chapters -1 -map 0:v -f webm -row-mt 1 -speed 0"
    )

    if webm.extra_params and "-c:v" in webm.extra_params:
        encoder = re.search(r"-c:v\s+(\w+)", webm.extra_params)
        if encoder:
            webm.encoder = encoder[1]

    # To sync the burned subtitles need output seeking
    if webm.lavfi and "subtitle" in webm.lavfi:
        webm.input_seeking = False

    if "libvpx" not in webm.encoder:
        webm.twopass = False
        webm.input_seeking = False
        webm.params = "-f matroska -map 0 -c copy -preset veryslow"

    start, stop = get_duration(webm.inputs[0])
    if stop is None:
        print(
            "An unexpected error occurred whilst retrieving "
            f"the metadata for the input file {webm.inputs[0].absolute()}",
            file=sys.stderr,
        )
        sys.exit(os.EX_SOFTWARE)

    if webm.ss is None:
        webm.ss = start
    if webm.to is None:
        webm.to = stop

    if webm.output:
        webm.output = pathlib.Path(webm.output)
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


def parse_argv():
    """Parses the command line arguments"""

    parser = argparse.ArgumentParser(
        description="Utility to encode quick webms with ffmpeg"
    )
    parser.add_argument(
        "--version", action="version", version=f"PureWebM {__version__}"
    )

    parser.add_argument(
        "input",
        nargs="+",
        help="the input file(s) to encode (NOTE: these are only for a single "
        "output file; to encode different files run this program multiple "
        "times, the files will be queued in the main process using a Unix "
        "socket)",
    )
    parser.add_argument(
        "--output",
        help="the output file, if not set, the filename will be generated "
        "using the filename of the input file plus a short MD5 hash and saved "
        f"in {pathlib.Path('~/Videos/PureWebM').expanduser()}",
    )

    parser.add_argument(
        "--encoder",
        default="libvpx-vp9",
        help="the encoder to use (default is libvpx-vp9)",
    )
    parser.add_argument(
        "--start_time", help="the start time offset (same as ffmpeg's -ss)"
    )
    parser.add_argument(
        "--stop_time", help="the stop time (same as ffmpeg's -to)"
    )
    parser.add_argument("--lavfi", help="the set of filters to pass to ffmpeg")
    parser.add_argument(
        "--size_limit",
        default=3,
        type=float,
        help="the size limit of the output file in megabytes, use 0 for no "
        "limit (default is 3)",
    )
    parser.add_argument(
        "--crf", default="24", help="the crf to use (default is 24)"
    )
    parser.add_argument(
        "--extra_params",
        help="the extra parameters to pass to ffmpeg, these will be appended "
        "to the end of command's parameters",
    )

    return vars(parser.parse_args())


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


if __name__ == "__main__":
    main()
