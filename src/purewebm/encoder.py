# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Module for handling the encodings"""

import pathlib
import subprocess  # nosec

from . import ffmpeg
from . import console


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
            duration = ffmpeg.get_seconds(webm.to) - ffmpeg.get_seconds(
                webm.ss
            )
            size_limit = webm.size_limit * 1024
            encoding += 1

            if webm.two_pass:
                first_pass, second_pass = ffmpeg.generate_args(webm)
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
                single_pass = ffmpeg.generate_args(webm)
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
    console.print_progress(
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
        console.print_progress(
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
        ffmpeg.run(
            command=command,
            color=color,
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
            color=color,
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

            console.print_progress(
                f"{color['red']}Retrying with bitrate "
                f"{round(bitrate)}K{color['endc']}\n",
                encoding,
                total_size,
            )

            # Find the last b:v index and update
            index = len(command) - command[::-1].index("-b:v")
            command[index] = str(round(bitrate, 3)) + "K"

            ffmpeg.run(
                command=command,
                color=color,
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
    console.print_progress(
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

    console.print_progress(
        f"{color['blue']}processing the single pass{color['endc']}",
        encoding,
        total_size,
    )

    # Single pass has no size limit, just constant quality with crf
    command.insert(command.index("-crf") + 2, "-b:v")
    command.insert(command.index("-b:v") + 1, "0")

    ffmpeg.run(
        command=command,
        color=color,
        size_limit=0,
        duration=duration,
        encoding=encoding,
        total_size=total_size,
        two_pass=False,
    )

    console.print_progress(
        f"{color['green']}100%{color['endc']}",
        encoding,
        total_size,
    )
