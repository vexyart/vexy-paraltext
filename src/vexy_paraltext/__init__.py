# this_file: src/vexy_paraltext/__init__.py
"""vexy-paraltext: build TMX translation memories from multilingual book editions."""

from vexy_paraltext.cli import main

__all__ = ["main"]

try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0.0.dev0"
