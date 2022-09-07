import importlib.metadata
import pathlib

__version__ = importlib.metadata.version(__package__)
CONFIG_PATH = pathlib.Path("~/.config/PureWebM").expanduser()
