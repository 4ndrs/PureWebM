# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Module for the preparation of the video namespace"""

import os
import sys
import time
import hashlib
import pathlib
from types import SimpleNamespace

from . import ffmpeg


def prepare(args):
    """Prepares the video namespace"""
    video = SimpleNamespace()

    video.inputs = args["input"]
    video.output = args["output"]
    video.encoder = args["encoder"]
    video.crf = args["crf"]
    video.size_limit = args["size_limit"]
    video.lavfi = args["lavfi"]
    video.ss = args["start_time"]
    video.to = args["stop_time"]
    video.extra_params = args["extra_params"]

    video.two_pass = True
    video.input_seeking = True
    video.params = (
        "-map_metadata -1 -map_chapters -1 -map 0:v -f webm "
        f"-row-mt 1 -cpu-used {args['cpu_used']} -deadline {args['deadline']}"
    )

    if video.extra_params:
        params = video.extra_params.split()
        video.encoder = (
            video.encoder
            if "-c:v" not in params
            else params[params.index("-c:v") + 1]
        )
        video.crf = (
            video.crf
            if "-crf" not in params
            else params[params.index("-crf") + 1]
        )

    if "libvpx" not in video.encoder:
        video.two_pass = False
        video.input_seeking = False
        video.params = ""

    if args["subtitles"]:
        if video.lavfi is None:
            video.lavfi = "subtitles=" + ffmpeg.escape_str(
                str(video.inputs[0])
            )
        elif "subtitles" not in video.lavfi:
            video.lavfi += ",subtitles=" + ffmpeg.escape_str(
                str(video.inputs[0])
            )

    # To sync the burned subtitles need output seeking
    if video.lavfi and "subtitle" in video.lavfi:
        video.input_seeking = False

    start, stop = ffmpeg.get_duration(video.inputs[0])
    if None in (start, stop):
        print(
            "An unexpected error occurred whilst retrieving "
            f"the metadata for the input file {video.inputs[0].absolute()}",
            file=sys.stderr,
        )
        sys.exit(os.EX_SOFTWARE)

    video.ss = start if video.ss is None else video.ss
    video.to = stop if video.to is None else video.to

    if video.output is None:
        if "http" in str(video.inputs[0]):
            input_filename = "http_vid"
        else:
            input_filename = video.inputs[0].absolute().stem
        video.output = _generate_filename(
            video.ss,
            video.to,
            video.extra_params,
            encoder=video.encoder,
            input_filename=input_filename,
            name_type=args["name_type"],
            save_path=pathlib.Path("~/Videos/PureWebM").expanduser(),
        )

    if not video.output.parent.exists():
        try:
            video.output.parent.mkdir(parents=True)
        except PermissionError:
            print(
                f"Unable to create folder {video.output.parent}, "
                "permission denied.",
                file=sys.stderr,
            )
            sys.exit(os.EX_CANTCREAT)

    return video


def _generate_filename(*seeds, **kwargs):
    """Generates the filename for the output file according to name_type

    name_type:
        unix  - generates the file name using the time since Epoch in
                milliseconds
        md5   - generates the file name using the input filename plus a short
                md5 hash generated with the seeds variables"""
    input_filename = kwargs["input_filename"]
    encoder = kwargs["encoder"]
    save_path = kwargs["save_path"]
    name_type = kwargs["name_type"]

    if name_type == "unix":
        filename = str(time.time_ns())[:16]
    elif name_type == "md5":
        md5 = hashlib.new("md5", usedforsecurity=False)
        for seed in seeds:
            md5.update(str(seed).encode())

        extension = ".webm" if "libvpx" in encoder else ".mkv"
        filename = input_filename + "_" + md5.hexdigest()[:10]

    extension = ".webm" if "libvpx" in encoder else ".mkv"
    filename += extension

    return save_path / filename
