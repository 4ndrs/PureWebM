# PureWebM

Originally written for [PureMPV](https://github.com/4ndrs/PureMPV), with this utility it is possible to encode webms from a given input, according to a restricted file size or a default CRF (Constant Rate Factor). If the utility is called whilst encoding, additional webm parameters will be put in a queue using Unix sockets.

## Usage
To encode a quick webm with the defaults:
```console
$ purewebm -ss 00:00:02.268 -to 00:00:10.310 -i "/tmp/Videos/nijinosaki.mkv" 
Encoding 1 of 1: 100%
```
Only the video stream will be mapped (no audio) with a size limit of 3MB, and saved under ```$HOME/Videos/PureWebM```.

To encode a webm with size limit of 6MB, burned subtitles, and opus audio:
```console
$ purewebm -i "/tmp/Videos/nijinosaki.mkv" --size_limit 6 -subs --extra_params '-map 0:a -c:a libopus -b:a 128k'
Encoding 1 of 1: 100%
```

It is possible to request usage instructions through the ```--help``` or ```-h``` option flags:
```console
$ purewebm --help
usage: purewebm [-h] [--version] (--status | --kill | --input INPUT) [--name_type {unix,md5}]
                [--subtitles] [--encoder ENCODER] [--start_time START_TIME] [--stop_time STOP_TIME]
                [--lavfi LAVFI] [--size_limit SIZE_LIMIT] [--crf CRF] [--cpu-used {0,1,2,3,4,5}]
                [--deadline {good,best}] [--extra_params EXTRA_PARAMS]
                [output]

Utility to encode quick webms with ffmpeg

positional arguments:
  output                the output file, if not set, the filename will be generated according to
                        --name_type and saved in $HOME/Videos/PureWebM

options:
  -h, --help            show this help message and exit
  --version, -v         show program's version number and exit
  --status              queries the main process and prints the current status
  --kill                sends the kill command to the main process; this will terminate all
                        encodings immediately, with no cleanups
  --input INPUT, -i INPUT
                        the input file to encode (NOTE: several files can be selected adding more
                        -i flags just like with ffmpeg, these will be only for a single output
                        file; to encode different files run this program multiple times, the files
                        will be queued in the main process using Unix sockets)
  --name_type {unix,md5}, -nt {unix,md5}
                        the filename type to be generated if the output file is not set: unix uses
                        the current time in microseconds since Epoch, md5 uses the filename of the
                        input file with a short MD5 hash attached (default is unix)
  --subtitles, -subs    burn the subtitles onto the output file; this flag will automatically use
                        the subtitles found in the first input file, to use a different file use
                        the -lavfi flag with the subtitles filter directly
  --encoder ENCODER, -c:v ENCODER
                        the encoder to use (default is libvpx-vp9)
  --start_time START_TIME, -ss START_TIME
                        the start time offset (same as ffmpeg's -ss)
  --stop_time STOP_TIME, -to STOP_TIME
                        the stop time (same as ffmpeg's -to)
  --lavfi LAVFI, -lavfi LAVFI
                        the set of filters to pass to ffmpeg
  --size_limit SIZE_LIMIT, -sl SIZE_LIMIT
                        the size limit of the output file in megabytes, use 0 for no limit (default
                        is 3)
  --crf CRF, -crf CRF   the crf to use (default is 24)
  --cpu-used {0,1,2,3,4,5}, -cpu-used {0,1,2,3,4,5}
                        the cpu-used for libvpx-vp9; a number between 0 and 5 inclusive, the higher
                        the number the faster the encoding will be with a quality trade-off
                        (default is 0)
  --deadline {good,best}, -deadline {good,best}
                        the deadline for libvpx-vp9; good is the recommended one, best has the best
                        compression efficiency but takes the most time (default is good)
  --extra_params EXTRA_PARAMS, -ep EXTRA_PARAMS
                        the extra parameters to pass to ffmpeg, these will be appended making it
                        possible to override some defaults
```

Logs are saved under ```$HOME/.config/PureWebM/PureWebM.log```

## Installation

It can be installed using pip:
```console
$ pip install purewebm
```
or
```bash
$ git clone https://github.com/4ndrs/PureWebM.git
$ cd PureWebM
$ pip install .
```
