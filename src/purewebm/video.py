# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Module for the preparation of the video namespace"""

import sys
import os
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
        "-map_metadata -1 -map_chapters -1 -map 0:v -f webm -row-mt 1 -speed 0"
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

    # To sync the burned subtitles need output seeking
    if video.lavfi and "subtitle" in video.lavfi:
        video.input_seeking = False

    if "libvpx" not in video.encoder:
        video.two_pass = False
        video.input_seeking = False
        video.params = ""

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
        video.output = generate_filename(
            video.ss,
            video.to,
            video.extra_params,
            encoder=video.encoder,
            input_filename=input_filename,
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


def generate_filename(*seeds, encoder, input_filename, save_path):
    """Generates the filename for the output file using an MD5 hash of the seed
    variables and the name of the input file"""
    md5 = hashlib.new("md5", usedforsecurity=False)
    for seed in seeds:
        md5.update(str(seed).encode())

    extension = ".webm" if "libvpx" in encoder else ".mkv"
    filename = input_filename + "_" + md5.hexdigest()[:10] + extension

    return save_path / filename
