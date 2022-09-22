#!/usr/bin/env python3
# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Main execution file"""

import sys
import os
import time
import pathlib
import argparse
from multiprocessing import Process, Event, Manager

from . import CONFIG_PATH, __version__

from . import ipc
from . import video
from . import config
from . import encoder
from . import console


def main():
    """Main function"""
    data = parse_argv()

    config.verify_config()
    socket = CONFIG_PATH / pathlib.Path("PureWebM.socket")

    if isinstance(data, str):
        if socket.exists() and "status" in data:
            try:
                queue = ipc.get_queue(socket)
                console.print_progress(
                    queue.status + "\n",
                    queue.encoding,
                    queue.total_size,
                    color=None,
                    no_clear=True,
                )
                sys.exit(os.EX_OK)
            except ConnectionRefusedError:
                print("Error connecting to the socket", file=sys.stderr)
                socket.unlink()
                sys.exit(os.EX_PROTOCOL)
        elif not socket.exists() and "status" in data:
            print("No current main process running", file=sys.stderr)
            sys.exit(os.EX_UNAVAILABLE)

    elif socket.exists():
        try:
            ipc.send(data, socket)
            print("Encoding information sent to the main process")
            sys.exit(os.EX_OK)
        except ConnectionRefusedError:
            print(
                "Error connecting to the socket\nStarting a new queue",
                file=sys.stderr,
            )
            socket.unlink()

    # Main process does not exist, starting a new queue
    manager = Manager()
    encoding_done = Event()

    queue = manager.Namespace()
    queue.items = manager.list()
    queue.total_size = manager.Value(int, 0)
    queue.encoding = manager.Value(int, 0)
    queue.status = manager.Value(str, "")

    queue.items.append(data)
    queue.total_size.set(queue.total_size.get() + 1)

    listener_p = Process(target=ipc.listen, args=(queue, socket))
    encoder_p = Process(target=encoder.encode, args=(queue, encoding_done))

    listener_p.start()
    encoder_p.start()

    try:
        while True:
            if encoding_done.is_set():
                listener_p.terminate()
                socket.unlink()
                sys.exit(os.EX_OK)

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nStopping (ctrl + c received)", file=sys.stderr)
        listener_p.terminate()
        encoder_p.terminate()
        sys.exit(-1)


def parse_argv():
    """Parses the command line arguments"""
    parser = argparse.ArgumentParser(
        description="Utility to encode quick webms with ffmpeg"
    )
    group = parser.add_mutually_exclusive_group(required=True)

    parser.add_argument(
        "--version", "-v", action="version", version=f"PureWebM {__version__}"
    )
    group.add_argument(
        "--status",
        action="store_true",
        default=argparse.SUPPRESS,
        help="queries the main process and prints the current status",
    )
    group.add_argument(
        "--input",
        "-i",
        action="append",
        help="the input file to encode (NOTE: several files can be selected "
        "adding more -i flags just like with ffmpeg, these will be only for a "
        "single output file; to encode different files run this program "
        "multiple times, the files will be queued in the main process using "
        "Unix sockets)",
    )
    parser.add_argument(
        "output",
        nargs="?",
        help="the output file, if not set, the filename will be generated "
        "according to --name_type and saved in "
        f"{pathlib.Path('~/Videos/PureWebM').expanduser()}",
    )
    parser.add_argument(
        "--name_type",
        "-nt",
        choices=("unix", "md5"),
        default="unix",
        help="the filename type to be generated if the output file is not "
        "set: unix uses the current time in microseconds since Epoch, md5 "
        "uses the filename of the input file with a short MD5 hash attached "
        "(default is unix)",
    )
    parser.add_argument(
        "--subtitles",
        "-subs",
        action="store_true",
        help="burn the subtitles onto the output file; this flag will "
        "automatically use the subtitles found in the first input file, "
        "to use a different file use the -lavfi flag with the subtitles "
        "filter directly",
    )
    parser.add_argument(
        "--encoder",
        "-c:v",
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

    args = vars(parser.parse_args())
    if "status" in args:
        return "status"

    if "http" in args["input"][0]:
        args["input"] = [pathlib.Path(url) for url in args["input"]]
    else:
        args["input"] = [
            pathlib.Path(path).absolute() for path in args["input"]
        ]
    if args["output"]:
        args["output"] = pathlib.Path(args["output"]).absolute()

    data = video.prepare(args)

    return data


if __name__ == "__main__":
    main()
