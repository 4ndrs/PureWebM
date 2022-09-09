#!/usr/bin/env python3
# Copyright (c) 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Main execution file"""

import sys
import os
import time
import pathlib
import argparse
from multiprocessing import Process, Event, Manager

from . import CONFIG_PATH, __version__
from .purewebm import enqueue, send, listen, verify_config
from .encoder import encode


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
    queue.total_size = manager.Value(int, 0)
    enqueue(queue, kwargs)

    listen_process = Process(target=listen, args=(queue, socket))
    encode_process = Process(target=encode, args=(queue, encoding_done))
    listen_process.start()
    encode_process.start()

    try:
        while True:
            if encoding_done.is_set():
                listen_process.terminate()
                socket.unlink()
                sys.exit(os.EX_OK)

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nStopping (ctrl + c received)", file=sys.stderr)
        listen_process.terminate()
        encode_process.terminate()
        sys.exit(-1)


def parse_argv():
    """Parses the command line arguments"""
    parser = argparse.ArgumentParser(
        description="Utility to encode quick webms with ffmpeg"
    )
    parser.add_argument(
        "--version", "-v", action="version", version=f"PureWebM {__version__}"
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
        "-o",
        help="the output file, if not set, the filename will be generated "
        "using the filename of the input file plus a short MD5 hash and saved "
        f"in {pathlib.Path('~/Videos/PureWebM').expanduser()}",
    )

    parser.add_argument(
        "--encoder",
        "-e",
        default="libvpx-vp9",
        help="the encoder to use (default is libvpx-vp9)",
    )
    parser.add_argument(
        "--start_time",
        "-ss",
        help="the start time offset (same as ffmpeg's -ss)",
    )
    parser.add_argument(
        "--stop_time",
        "-to",
        help="the stop time (same as ffmpeg's -to)",
    )
    parser.add_argument(
        "--lavfi",
        "-lavfi",
        help="the set of filters to pass to ffmpeg",
    )
    parser.add_argument(
        "--size_limit",
        "-sl",
        default=3,
        type=float,
        help="the size limit of the output file in megabytes, use 0 for no "
        "limit (default is 3)",
    )
    parser.add_argument(
        "--crf", "-crf", default="24", help="the crf to use (default is 24)"
    )
    parser.add_argument(
        "--extra_params",
        "-ep",
        help="the extra parameters to pass to ffmpeg, these will be appended "
        "making it possible to override some defaults",
    )

    kwargs = vars(parser.parse_args())
    if "http" in kwargs["input"][0]:
        kwargs["input"] = [pathlib.Path(url) for url in kwargs["input"]]
    else:
        kwargs["input"] = [
            pathlib.Path(path).absolute() for path in kwargs["input"]
        ]
    if kwargs["output"]:
        kwargs["output"] = pathlib.Path(kwargs["output"]).absolute()

    return kwargs


if __name__ == "__main__":
    main()