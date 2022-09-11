# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Module for handling the encodings"""

import pathlib
from subprocess import CalledProcessError  # nosec

from . import ffmpeg
from . import console


def encode(queue, encoding_done):
    """Processes the encodings for the webms in the queue list"""
    encoding = 0

    try:
        while queue.items:
            webm = queue.items.pop(0)
            duration = ffmpeg.get_seconds(webm.to) - ffmpeg.get_seconds(
                webm.ss
            )
            size_limit = webm.size_limit * 1024
            encoding += 1

            if webm.two_pass:
                first_pass, second_pass = ffmpeg.generate_args(webm)
                _encode_two_pass(
                    first_command=first_pass,
                    second_command=second_pass,
                    output_file=webm.output,
                    size_limit=size_limit,
                    duration=duration,
                    crf=webm.crf,
                    encoding=encoding,
                    total_size=queue.total_size,
                )

            else:
                single_pass = ffmpeg.generate_args(webm)
                _encode_single_pass(
                    command=single_pass,
                    duration=duration,
                    encoding=encoding,
                    total_size=queue.total_size,
                )

    except KeyboardInterrupt:
        pass  # The keyboard interrupt message is handled by main()
    finally:
        encoding_done.set()


def _encode_two_pass(**kwargs):
    """Handles the two pass encoding"""
    first_command = kwargs["first_command"]
    second_command = kwargs["second_command"]
    output_file = kwargs["output_file"]
    size_limit = kwargs["size_limit"]
    duration = kwargs["duration"]
    crf = kwargs["crf"]
    encoding = kwargs["encoding"]
    total_size = kwargs["total_size"]

    if _run_first_pass(first_command, encoding, total_size):
        _run_second_pass(
            command=second_command,
            crf=crf,
            output_file=output_file,
            encoding=encoding,
            size_limit=size_limit,
            total_size=total_size,
            duration=duration,
        )


def _run_first_pass(command, encoding, total_size):
    """Returns True if the first pass processes successfully, False
    otherwise"""
    console.print_progress("processing the first pass", encoding, total_size)

    try:
        ffmpeg.run(first_pass=True, command=command)

    except CalledProcessError as error:
        console.print_error(
            where="first pass",
            encoding=encoding,
            total_size=total_size,
            cmd=error.cmd,
            output=error.stderr,
        )
        return False
    return True


def _run_second_pass(**kwargs):
    """Processes the second pass. If there is no size limit, it will trigger
    constant quality mode setting b:v 0 and using just the crf. If there is a
    size limit, it will try to encode the file again and again with a
    recalculated bitrate until it is within the size limit."""
    command = kwargs["command"]
    crf = kwargs["crf"]
    output_file = kwargs["output_file"]
    encoding = kwargs["encoding"]
    size_limit = kwargs["size_limit"]
    total_size = kwargs["total_size"]
    duration = kwargs["duration"]

    bitrate = 0

    # insert -b:v 0 after the crf to trigger constant quality mode
    command.insert(command.index("-crf") + 2, "-b:v")
    command.insert(command.index("-b:v") + 1, "0")

    if not size_limit:
        ffmpeg.run(
            command=command,
            size_limit=0,
            duration=duration,
            encoding=encoding,
            total_size=total_size,
            two_pass=True,
        )

    else:
        # Try encoding just in constant quality mode first
        ffmpeg.run(
            command=command,
            size_limit=size_limit,
            duration=duration,
            encoding=encoding,
            total_size=total_size,
            two_pass=True,
        )

        # Check that the file generated is within the limit
        size = output_file.stat().st_size / 1024
        if size > size_limit:
            percent = ((size - size_limit) / size_limit) * 100
            percent_txt = (
                round(percent) if round(percent) > 1 else round(percent, 3)
            )
            console.print_progress(
                f"File size is greater than the limit by {percent_txt}% with "
                f"crf {crf}\n",
                encoding,
                total_size,
                color="red",
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

            console.print_progress(
                f"Retrying with bitrate {round(bitrate)}K\n",
                encoding,
                total_size,
                color="red",
            )

            # Find the last b:v index and update
            index = len(command) - command[::-1].index("-b:v")
            command[index] = str(round(bitrate, 3)) + "K"

            ffmpeg.run(
                command=command,
                size_limit=size_limit,
                duration=duration,
                encoding=encoding,
                total_size=total_size,
                two_pass=True,
            )

            # Check that the file size is within the limit
            size = output_file.stat().st_size / 1024
            if size > size_limit:
                percent = ((size - size_limit) / size_limit) * 100
                percent_txt = (
                    round(percent) if round(percent) > 1 else round(percent, 3)
                )
                console.print_progress(
                    f"File size is greater than the limit by {percent_txt}% "
                    f"with bitrate {round(bitrate)}K\n",
                    encoding,
                    total_size,
                    color="red",
                )

            else:
                failed = False

    # Two-pass encoding done
    console.print_progress("100%\n", encoding, total_size, color="green")

    # Delete the first pass log file
    pathlib.Path("PureWebM2pass-0.log").unlink()


def _encode_single_pass(**kwargs):
    """Handles the single pass"""
    command = kwargs["command"]
    duration = kwargs["duration"]
    encoding = kwargs["encoding"]
    total_size = kwargs["total_size"]

    console.print_progress(
        "processing the single pass", encoding, total_size, color="blue"
    )

    # Single pass has no size limit, just constant quality with crf
    command.insert(command.index("-crf") + 2, "-b:v")
    command.insert(command.index("-b:v") + 1, "0")

    try:
        ffmpeg.run(
            command=command,
            size_limit=0,
            duration=duration,
            encoding=encoding,
            total_size=total_size,
            two_pass=False,
        )
    except CalledProcessError as error:
        console.print_error(
            "single pass",
            encoding,
            total_size,
            cmd=error.cmd,
            output=error.stderr,
        )
    else:
        console.print_progress("100%\n", encoding, total_size, color="green")
