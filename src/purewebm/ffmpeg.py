# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Module for the interfacing with ffmpeg"""

import os
import re
import signal
import shutil
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
        color       - the ANSI escape codes for colors
        size_limit  - the size limit to stay within in kilobytes
        duration    - the duration of the output file in seconds
        encoding    - the number of the current video in the queue list
        total_size  - the total size of the queue list
        two_pass    - the video's two_pass boolean"""
    if first_pass:
        try:
            subprocess.run(  # nosec
                kwargs["command"],
                check=True,
                capture_output=True,
            )

        except subprocess.CalledProcessError as error:
            cmd = " ".join(str(arg) for arg in kwargs["command"])
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
            output = ""
            for line in task.stdout:
                output += line
                progress, size = get_progress(line)
                if progress is None:
                    continue
                if kwargs["size_limit"] and kwargs["two_pass"]:
                    if size > kwargs["size_limit"]:
                        task.kill()
                percent = round(
                    get_seconds(progress) * 100 / kwargs["duration"]
                )
                console.print_progress(
                    f"{kwargs['color']['blue']}{percent}%"
                    f"{kwargs['color']['endc']}",
                    kwargs["encoding"],
                    kwargs["total_size"],
                )

            task.communicate()
            if task.returncode not in (os.EX_OK, -abs(signal.SIGKILL)):
                cmd = " ".join(str(arg) for arg in kwargs["command"])
                raise subprocess.CalledProcessError(
                    returncode=task.returncode,
                    cmd=cmd,
                    stderr=output,
                )


def generate_args(webm):
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

    ffmpeg_args = [shutil.which("ffmpeg"), "-hide_banner"] + ffmpeg_args
    ffmpeg_args += webm.params.split() + ["-c:v", webm.encoder]
    ffmpeg_args += ["-lavfi", webm.lavfi] if webm.lavfi else []
    ffmpeg_args += ["-crf", webm.crf]
    ffmpeg_args += webm.extra_params.split() if webm.extra_params else []

    if webm.two_pass:
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


def get_seconds(timestamp):
    """Converts timestamp to seconds with 3 decimal places"""
    seconds = sum(
        (
            float(num) * (60**index)
            for index, num in enumerate(reversed(timestamp.split(":")))
        )
    )

    return round(seconds, 3)


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


def get_error(ffmpeg_output):
    """Parses and returns the error lines generated by ffmpeg"""
    pattern = r"Press.*to stop.* for help(.*)"
    found = re.search(pattern, ffmpeg_output, re.DOTALL)

    if found:
        return found[1].strip()
    return None
