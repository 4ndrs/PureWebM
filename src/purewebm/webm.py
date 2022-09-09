# Copyright (c) 2022 4ndrs <andres.degozaru@gmail.com>
# SPDX-License-Identifier: MIT
"""Module for the preparation of the webm namespace"""

import sys
import os
import re
import hashlib
import pathlib

from . import ffmpeg


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

    webm.two_pass = True
    webm.input_seeking = True
    webm.params = (
        "-map_metadata -1 -map_chapters -1 -map 0:v -f webm -row-mt 1 -speed 0"
    )

    if webm.extra_params:
        if "-c:v" in webm.extra_params:
            encoder = re.search(r"-c:v\s+(\w+)", webm.extra_params)
            webm.encoder = encoder if encoder else webm.encoder
        if "-crf" in webm.extra_params:
            crf = re.search(r"-crf\s+(\d+)", webm.extra_params)
            crf = crf if crf else webm.crf

    # To sync the burned subtitles need output seeking
    if webm.lavfi and "subtitle" in webm.lavfi:
        webm.input_seeking = False

    if "libvpx" not in webm.encoder:
        webm.two_pass = False
        webm.input_seeking = False
        webm.params = "-f matroska -map 0 -c copy -preset veryslow"

    start, stop = ffmpeg.get_duration(webm.inputs[0])
    if None in (start, stop):
        print(
            "An unexpected error occurred whilst retrieving "
            f"the metadata for the input file {webm.inputs[0].absolute()}",
            file=sys.stderr,
        )
        sys.exit(os.EX_SOFTWARE)

    webm.ss = start if webm.ss is None else webm.ss
    webm.to = stop if webm.to is None else webm.to

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


def generate_filename(*seeds, encoder, input_filename, save_path):
    """Generates the filename for the output file using an MD5 hash of the seed
    variables and the name of the input file"""
    md5 = hashlib.new("md5", usedforsecurity=False)
    for seed in seeds:
        md5.update(str(seed).encode())

    extension = ".webm" if "libvpx" in encoder else ".mkv"
    filename = input_filename + "_" + md5.hexdigest()[:10] + extension

    return save_path / filename
