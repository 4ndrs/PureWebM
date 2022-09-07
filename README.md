# PureWebM

Originally written for [PureMPV](https://github.com/4ndrs/PureMPV), with this utility it is possible to encode webms from a given input, according to a restricted file size or a default CRF (Constant Rate Factor). If the utility is called whilst encoding, additional webm parameters will be put in a queue using a Unix socket for IPC.

## Usage

It is possible to request usage instructions through the ```--help``` or ```-h``` argument option flags when the program is installed:
```bash
$ purewebm --help
usage: purewebm [-h] [--version] [--output OUTPUT] [--encoder ENCODER] [--start_time START_TIME]
                [--stop_time STOP_TIME] [--lavfi LAVFI] [--size_limit SIZE_LIMIT] [--crf CRF]
                [--extra_params EXTRA_PARAMS]
                input [input ...]

Utility to encode quick webms with ffmpeg

positional arguments:
  input                 the input file(s) to encode (NOTE: these are only for a single output file; to encode different
                        files run this program multiple times, the files will be queued in the main process using a
                        Unix socket)

options:
  -h, --help            show this help message and exit
  --version, -v         show program's version number and exit
  --output OUTPUT, -o OUTPUT
                        the output file, if not set, the filename will be generated using the filename of the input
                        file plus a short MD5 hash and saved in $HOME/Videos/PureWebM
  --encoder ENCODER, -e ENCODER
                        the encoder to use (default is libvpx-vp9)
  --start_time START_TIME, -ss START_TIME
                        the start time offset (same as ffmpeg's -ss)
  --stop_time STOP_TIME, -to STOP_TIME
                        the stop time (same as ffmpeg's -to)
  --lavfi LAVFI, -lavfi LAVFI
                        the set of filters to pass to ffmpeg
  --size_limit SIZE_LIMIT, -sl SIZE_LIMIT
                        the size limit of the output file in megabytes, use 0 for no limit (default is 3)
  --crf CRF, -crf CRF   the crf to use (default is 24)
  --extra_params EXTRA_PARAMS, -ep EXTRA_PARAMS
                        the extra parameters to pass to ffmpeg, these will be appended making it possible to override
                        some defaults

```

## Installation

It can be installed using pip:
```bash
$ pip install purewebm
```
or
```bash
$ git clone https://github.com/4ndrs/PureWebM.git
$ cd PureWebM
$ pip install .
```
