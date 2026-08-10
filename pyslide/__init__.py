# -*- coding: utf-8 -*-

import os, sys

__all__ = ["__version__", ]

# importlib.metadata replaces pkg_resources (removed in newer setuptools).
try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("pyslide")
except Exception:
    # Fallback if the package metadata is not installed.
    __version__ = "0.5.0"

from . import contour
from . import patch
from . import pyramid
