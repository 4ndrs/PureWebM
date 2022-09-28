# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Module for the interfacing with ffmpeg"""

import os
import re
import signal
import shutil
import logging
import subprocess  # nosec

from . import console


def run(first_pass=False, **kwargs):
    """Runs ffmpeg with the specified command and prints the progress on the
    screen

    Keyword arguments:
        first_pass  - whether or not this will be run as first pass

    Keyword arguments for first pass:
        command     - the list to pass to subprocess, generated with
                      generate_args()

    Keyword arguments for other passes:
        command     - the list to pass to subprocess, generated with
                      generate_args()
        size_limit  - the size limit to stay within in kilobytes
        duration    - the duration of the output file in seconds
        status      - the Manager.Value() object to write the current progress
        encoding    - the number of the current video in the queue list
        total_size  - the total size of the queue list
        ffmpeg_pid  - the Manager.Value() to write the ffmpeg pid
        two_pass    - the video's two_pass boolean"""
    cmd = " ".join(str(arg) for arg in kwargs["command"])
    logging.info("Executing: %s", cmd)
    if first_pass:
        try:
            subprocess.run(  # nosec
                kwargs["command"],
                check=True,
                capture_output=True,
            )

        except subprocess.CalledProcessError as error:
            logging.error(
                "Error encountered running the ffmpeg command, returned "
                "error code: %i",
                error.returncode,
            )
            raise subprocess.CalledProcessError(
                returncode=error.returncode,
                cmd=cmd,
                stderr=error.stderr.decode(),
            )

    else:
        with subprocess.Popen(  # nosec
            kwargs["command"],
            universal_newlines=True,
            stderr=subprocess.STDOUT,
            stdout=subprocess.PIPE,
            bufsize=1,
        ) as task:
            kwargs["ffmpeg_pid"].set(task.pid)
            output = ""
            tmp_status = ""
            cq_mode = (  # constant quality mode
                kwargs["command"][kwargs["command"].index("-b:v") + 1] == "0"
            )
            for line in task.stdout:
                output += line
                time, size = _get_progress(line)
                if time is None:
                    continue
                if (
                    cq_mode
                    and kwargs["size_limit"]
                    and kwargs["two_pass"]
                    and size > kwargs["size_limit"]
                ):
                    task.kill()
                percent = round(get_seconds(time) * 100 / kwargs["duration"])
                kwargs["status"].set(f"{percent}%")
                if kwargs["status"].get() != tmp_status:
                    logging.info(
                        "Encoding %i of %i: %s",
                        kwargs["encoding"],
                        kwargs["total_size"].get(),
                        kwargs["status"].get(),
                    )
                    tmp_status = kwargs["status"].get()
                console.print_progress(
                    kwargs["status"].get(),
                    kwargs["encoding"],
                    kwargs["total_size"].get(),
                    color="blue",
                )

            task.communicate()
            kwargs["ffmpeg_pid"].set(None)
            if task.returncode not in (os.EX_OK, -abs(signal.SIGKILL)):
                logging.error(
                    "Error encountered running the ffmpeg command, returned "
                    "error code: %i",
                    task.returncode,
                )
                raise subprocess.CalledProcessError(
                    returncode=task.returncode,
                    cmd=cmd,
                    stderr=output,
                )


def generate_args(webm):
    """Generates the ffmpeg args to pass to subprocess"""
    args = []

    # if input seeking put the timestamps in front of the inputs
    if webm.input_seeking:
        for path in webm.inputs:
            args += ["-ss", webm.ss, "-to", webm.to, "-i", path]
    else:
        for path in webm.inputs:
            args += ["-i", path]
        args += ["-ss", webm.ss, "-to", webm.to]

    args = [shutil.which("ffmpeg"), "-hide_banner"] + args
    args += webm.params.split() + ["-c:v", webm.encoder]
    args += ["-lavfi", webm.lavfi] if webm.lavfi else []
    args += ["-crf", webm.crf]
    args += webm.extra_params.split() if webm.extra_params else []

    if webm.two_pass:
        first_pass = args + [
            "-pass",
            "1",
            "-passlogfile",
            "PureWebM2pass",
            "/dev/null",
            "-y",
        ]
        second_pass = args + [
            "-pass",
            "2",
            "-passlogfile",
            "PureWebM2pass",
            webm.output,
            "-y",
        ]
        return first_pass, second_pass

    return args + [webm.output, "-y"]


def escape_str(string):
    """Escapes the special characters in string for use in ffmpeg filters"""
    # Square brackets
    string = string.replace("[", r"\[").replace("]", r"\]")

    # Single quotes
    string = string.replace("'", r"\\\'")

    # Semicolon
    string = string.replace(";", r"\;")

    # Colon
    string = string.replace(":", r"\\:")

    # Comma
    string = string.replace(",", r"\,")

    return string


def get_seconds(timestamp):
    """Converts timestamp to seconds with 3 decimal places"""
    seconds = sum(
        (
            float(num) * (60**index)
            for index, num in enumerate(reversed(timestamp.split(":")))
        )
    )

    return round(seconds, 3)


def _get_progress(line):
    """Parses and returns the time progress and the size in bytes printed by
    ffmpeg"""
    pattern = (
        r".*size=\s+(?P<size>\d+)kB\s+"
        r"time=(?P<time>\d{2,}:\d{2}:\d{2}\.\d+)"
    )
    found = re.search(pattern, line)
    time, size = (
        (None, None)
        if not found
        else (found.groupdict()["time"], int(found.groupdict()["size"]) * 1024)
    )
    return time, size


def get_duration(file_path):
    """Retrieves the file's start and stop times with ffmpeg"""
    pattern = (
        r"Duration:\s+(?P<stop>\d{2,}:\d{2}:\d{2}\.\d+),\s+"
        r"start:\s+(?P<start>-?\d+\.\d+)"
    )

    ffmpeg_output = subprocess.run(  # nosec
        ["ffmpeg", "-hide_banner", "-i", file_path],
        check=False,
        capture_output=True,
    ).stderr.decode()

    found = re.search(pattern, ffmpeg_output)

    start, stop = (
        (None, None)
        if not found
        else (found.groupdict()["start"], found.groupdict()["stop"])
    )
    return start, stop


def _get_error(ffmpeg_output):
    """Parses and returns the error lines generated by ffmpeg"""
    pattern = r"Press.*to stop.* for help(.*)"
    found = re.search(pattern, ffmpeg_output, re.DOTALL)

    if found:
        return found[1].strip()
    return None
