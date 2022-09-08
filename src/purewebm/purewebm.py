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


def encode(queue, encoding_done):
    """Processes the encodings for the webms in the queue list"""
    encoding = 0
    color = {
        "green": "\033[1;92m",
        "blue": "\033[1;94m",
        "red": "\033[1;91m",
        "endc": "\033[0m",
    }

    try:
        while queue.items:
            webm = queue.items.pop(0)
            duration = get_seconds(webm.to) - get_seconds(webm.ss)
            size_limit = webm.size_limit * 1024
            encoding += 1

            if webm.twopass:
                first_pass, second_pass = generate_ffmpeg_args(webm)
                encode_two_pass(
                    first_command=first_pass,
                    second_command=second_pass,
                    output_file=webm.output,
                    size_limit=size_limit,
                    duration=duration,
                    crf=webm.crf,
                    encoding=encoding,
                    color=color,
                    total_size=queue.total_size,
                )

            else:
                single_pass = generate_ffmpeg_args(webm)
                encode_single_pass(
                    command=single_pass,
                    color=color,
                    duration=duration,
                    encoding=encoding,
                    total_size=queue.total_size,
                )

    except KeyboardInterrupt:
        pass  # The keyboard interrupt message is handled by main()
    finally:
        print(end="\n")
        encoding_done.set()


def encode_two_pass(**kwargs):
    """Handles the two pass encoding"""
    first_command = kwargs["first_command"]
    second_command = kwargs["second_command"]
    output_file = kwargs["output_file"]
    size_limit = kwargs["size_limit"]
    duration = kwargs["duration"]
    crf = kwargs["crf"]
    encoding = kwargs["encoding"]
    color = kwargs["color"]
    total_size = kwargs["total_size"]

    if run_first_pass(first_command, encoding, color, total_size):
        run_second_pass(
            command=second_command,
            crf=crf,
            output_file=output_file,
            encoding=encoding,
            color=color,
            size_limit=size_limit,
            total_size=total_size,
            duration=duration,
        )


def run_first_pass(command, encoding, color, total_size):
    """Returns True if the first pass processes successfully, False
    otherwise"""
    print_progress(
        f"{color['blue']}processing the first pass{color['endc']}",
        encoding,
        total_size,
    )

    try:
        subprocess.run(  # nosec
            command,
            check=True,
            capture_output=True,
        )

    except subprocess.CalledProcessError as error:
        print_progress(
            f"{color['red']}Error running the first pass:",
            encoding,
            total_size,
        )
        print(f"\n{error.stderr.decode()}{color['endc']}", end="")
        return False

    return True


def run_second_pass(**kwargs):
    """Processes the second pass. If there is no size limit, it will trigger
    constant quality mode setting b:v 0 and using just the crf. If there is a
    size limit, it will try to encode the file again and again with a
    recalculated bitrate until it is within the size limit."""
    command = kwargs["command"]
    crf = kwargs["crf"]
    output_file = kwargs["output_file"]
    encoding = kwargs["encoding"]
    color = kwargs["color"]
    size_limit = kwargs["size_limit"]
    total_size = kwargs["total_size"]
    duration = kwargs["duration"]

    bitrate = 0

    # insert -b:v 0 after the crf to trigger constant quality mode
    command.insert(command.index("-crf") + 2, "-b:v")
    command.insert(command.index("-b:v") + 1, "0")

    if not size_limit:
        run_ffmpeg(
            command=command,
            color=color,
            size_limit=0,
            duration=duration,
            encoding=encoding,
            total_size=total_size,
            twopass=True,
        )

    else:
        # Try encoding just in constant quality mode first
        run_ffmpeg(
            command=command,
            color=color,
            size_limit=size_limit,
            duration=duration,
            encoding=encoding,
            total_size=total_size,
            twopass=True,
        )

        # Check that the file generated is within the limit
        size = output_file.stat().st_size / 1024
        if size > size_limit:
            percent = ((size - size_limit) / size_limit) * 100
            percent_txt = (
                round(percent) if round(percent) > 1 else round(percent, 3)
            )
            print_progress(
                f"{color['red']}File size is "
                "greater than the limit by "
                f"{percent_txt}% with crf {crf}"
                f"{color['endc']}\n",
                encoding,
                total_size,
            )

            # Set the crf to 10, for a targeted bitrate next
            if crf != "10":
                command[command.index("-crf") + 1] = "10"

            percent = None
            failed = True

        else:
            failed = False

        while failed:
            if percent:
                bitrate -= percent / 100 * bitrate
            else:
                bitrate = size_limit / duration * 8 * 1024 / 1000

            print_progress(
                f"{color['red']}Retrying with bitrate "
                f"{round(bitrate)}K{color['endc']}\n",
                encoding,
                total_size,
            )

            # Find the last b:v index and update
            index = len(command) - command[::-1].index("-b:v")
            command[index] = str(round(bitrate, 3)) + "K"

            run_ffmpeg(
                command=command,
                color=color,
                size_limit=size_limit,
                duration=duration,
                encoding=encoding,
                total_size=total_size,
                twopass=True,
            )

            # Check that the file size is within the limit
            size = output_file.stat().st_size / 1024
            if size > size_limit:
                percent = ((size - size_limit) / size_limit) * 100
                percent_txt = (
                    round(percent) if round(percent) > 1 else round(percent, 3)
                )
                print_progress(
                    f"{color['red']}File size is "
                    f"greater than the limit by "
                    f"{percent_txt}% with bitrate "
                    f"{round(bitrate)}K{color['endc']}\n",
                    encoding,
                    total_size,
                )

            else:
                failed = False

    # Two-pass encoding done
    print_progress(
        f"{color['green']}100%{color['endc']}",
        encoding,
        total_size,
    )

    # Delete the first pass log file
    pathlib.Path("PureWebM2pass-0.log").unlink()


def encode_single_pass(**kwargs):
    """Handles the single pass"""
    command = kwargs["command"]
    color = kwargs["color"]
    duration = kwargs["duration"]
    encoding = kwargs["encoding"]
    total_size = kwargs["total_size"]

    print_progress(
        f"{color['blue']}processing the single pass{color['endc']}",
        encoding,
        total_size,
    )

    # Single pass has no size limit, just constant quality with crf
    command.insert(command.index("-crf") + 2, "-b:v")
    command.insert(command.index("-b:v") + 1, "0")

    run_ffmpeg(
        command=command,
        color=color,
        size_limit=0,
        duration=duration,
        encoding=encoding,
        total_size=total_size,
        twopass=False,
    )

    print_progress(
        f"{color['green']}100%{color['endc']}",
        encoding,
        total_size,
    )


def run_ffmpeg(**kwargs):
    """Runs ffmpeg with the specified command and prints the progress on the
    screen"""
    command = kwargs["command"]
    color = kwargs["color"]
    limit = kwargs["size_limit"]
    duration = kwargs["duration"]
    encoding = kwargs["encoding"]
    total_size = kwargs["total_size"]
    twopass = kwargs["twopass"]

    with subprocess.Popen(  # nosec
        command,
        universal_newlines=True,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        bufsize=1,
    ) as task:
        for line in task.stdout:
            progress, size = get_progress(line)
            if progress is None:
                continue
            if limit and twopass:
                if size > limit:
                    task.terminate()
            percent = round(get_seconds(progress) * 100 / duration)
            print_progress(
                f"{color['blue']}{percent}%{color['endc']}",
                encoding,
                total_size,
            )


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

    if webm.extra_params:
        if "-c:v" in webm.extra_params:
            encoder = re.search(r"-c:v\s+(\w+)", webm.extra_params)
            if encoder:
                webm.encoder = encoder[1]
        if "-crf" in webm.extra_params:
            crf = re.search(r"-crf\s+(\d+)", webm.extra_params)
            if crf:
                webm.crf = crf[1]

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

    ffmpeg_args = ["ffmpeg", "-hide_banner"] + ffmpeg_args
    ffmpeg_args += webm.params.split() + ["-c:v", webm.encoder]
    ffmpeg_args += ["-lavfi", webm.lavfi] if webm.lavfi else []
    ffmpeg_args += ["-crf", webm.crf]
    ffmpeg_args += webm.extra_params.split() if webm.extra_params else []

    if webm.twopass:
        first_pass = ffmpeg_args + [
            "-pass",
            "1",
            "-passlogfile",
            "PureWebM2pass",
            "/dev/null",
            "-y",
        ]
        second_pass = ffmpeg_args + [
            "-pass",
            "2",
            "-passlogfile",
            "PureWebM2pass",
            webm.output,
            "-y",
        ]
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


def get_progress(line):
    """Parses and returns the time progress and size printed by ffmpeg"""
    pattern = (
        r".*size=\s+(?P<size>\d+)kB\s+"
        r"time=(?P<time>\d{2,}:\d{2}:\d{2}\.\d+)"
    )
    found = re.search(pattern, line)
    if found:
        found = found.groupdict()
        return found["time"], int(found["size"])
    return None, None


def get_error(ffmpeg_output):
    """Parses and returns the error lines generated by ffmpeg"""
    pattern = r"Press.*to stop.* for help(.*)"
    found = re.search(pattern, ffmpeg_output, re.DOTALL)

    if found:
        return found[1].strip()
    return None


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


def print_progress(message, progress, total_size):
    """Prints the encoding progress with a customized message"""
    clear_line = "\r\033[K"
    print(
        f"{clear_line}Encoding {progress} of {total_size.get()}: {message}",
        end="",
        flush=True,
    )


if __name__ == "__main__":
    main()
