# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Module for handling the encodings"""

import pathlib
from subprocess import CalledProcessError  # nosec

from . import ffmpeg
from . import console


def encode(queue, encoding_done):
    """Processes the encodings for the webms in the queue list"""
    encoding = queue.encoding
    total_size = queue.total_size
    status = queue.status

    try:
        while queue.items:
            webm = queue.items.pop(0)
            duration = ffmpeg.get_seconds(webm.to) - ffmpeg.get_seconds(
                webm.ss
            )
            size_limit = webm.size_limit * 1024**2  # convert to bytes
            encoding.set(encoding.get() + 1)

            if webm.two_pass:
                first_pass, second_pass = ffmpeg.generate_args(webm)
                _encode_two_pass(
                    first_command=first_pass,
                    second_command=second_pass,
                    output_file=webm.output,
                    size_limit=size_limit,
                    duration=duration,
                    crf=webm.crf,
                    encoding=encoding.get(),
                    total_size=total_size,
                    status=status,
                )

            else:
                single_pass = ffmpeg.generate_args(webm)
                _encode_single_pass(
                    command=single_pass,
                    duration=duration,
                    encoding=encoding.get(),
                    total_size=total_size,
                    status=status,
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
    status = kwargs["status"]

    if _run_first_pass(first_command, encoding, total_size, status):
        _run_second_pass(
            command=second_command,
            crf=crf,
            output_file=output_file,
            status=status,
            encoding=encoding,
            size_limit=size_limit,
            total_size=total_size,
            duration=duration,
        )


def _run_first_pass(command, encoding, total_size, status):
    """Returns True if the first pass processes successfully, False
    otherwise"""
    status.set("processing the first pass")
    console.print_progress(status.get(), encoding, total_size.get())

    try:
        ffmpeg.run(first_pass=True, command=command)

    except CalledProcessError as error:
        console.print_error(
            where="first pass",
            encoding=encoding,
            total_size=total_size.get(),
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
    status = kwargs["status"]
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
            status=status,
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
            status=status,
            encoding=encoding,
            total_size=total_size,
            two_pass=True,
        )

        # Check that the file generated is within the limit
        size = output_file.stat().st_size
        if size > size_limit:
            percent = ((size - size_limit) / size_limit) * 100
            percent_txt = (
                round(percent) if round(percent) > 1 else round(percent, 3)
            )
            status.set(
                f"File size is greater than the limit by {percent_txt}% with "
                f"crf {crf}",
            )
            console.print_progress(
                status.get() + "\n", encoding, total_size.get(), color="red"
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
                # set minimum percent of 0.020
                percent = 0.020 if percent < 0.020 else percent
                bitrate -= round(percent / 100 * bitrate)
            else:
                bitrate = round(size_limit / duration * 8)

            status.set(
                f"Retrying with bitrate {round(bitrate / 1000, 2)}K",
            )
            console.print_progress(
                status.get() + "\n", encoding, total_size.get(), color="red"
            )

            # Find the last b:v index and update
            index = len(command) - command[::-1].index("-b:v")
            command[index] = str(bitrate)

            ffmpeg.run(
                command=command,
                size_limit=size_limit,
                duration=duration,
                status=status,
                encoding=encoding,
                total_size=total_size,
                two_pass=True,
            )

            # Check that the file size is within the limit
            size = output_file.stat().st_size
            if size > size_limit:
                percent = ((size - size_limit) / size_limit) * 100
                percent_txt = (
                    round(percent) if round(percent) > 1 else round(percent, 3)
                )
                status.set(
                    f"File size is greater than the limit by {percent_txt}% "
                    f"with bitrate {round(bitrate / 1000, 2)}K",
                )
                console.print_progress(
                    status.get() + "\n",
                    encoding,
                    total_size.get(),
                    color="red",
                )

            else:
                failed = False

    # Two-pass encoding done
    status.set("100%")
    console.print_progress(
        status.get() + "\n", encoding, total_size.get(), color="green"
    )

    # Delete the first pass log file
    pathlib.Path("PureWebM2pass-0.log").unlink()


def _encode_single_pass(**kwargs):
    """Handles the single pass"""
    command = kwargs["command"]
    duration = kwargs["duration"]
    encoding = kwargs["encoding"]
    total_size = kwargs["total_size"]
    status = kwargs["status"]

    status.set("processing the single pass")
    console.print_progress(
        status.get(), encoding, total_size.get(), color="blue"
    )

    # Single pass has no size limit, just constant quality with crf
    command.insert(command.index("-crf") + 2, "-b:v")
    command.insert(command.index("-b:v") + 1, "0")

    try:
        ffmpeg.run(
            command=command,
            size_limit=0,
            duration=duration,
            status=status,
            encoding=encoding,
            total_size=total_size,
            two_pass=False,
        )
    except CalledProcessError as error:
        console.print_error(
            "single pass",
            encoding,
            total_size.get(),
            cmd=error.cmd,
            output=error.stderr,
        )
    else:
        status.set("100%")
        console.print_progress(
            status.get() + "\n", encoding, total_size.get(), color="green"
        )
