# -*- coding: utf-8 -*-
""" Optional PolypStrik remote-annotation client."""

from .annotate import annotate_with_polypstrik
from .client import (
    PolypStrikAPIError,
    PolypStrikAuthError,
    PolypStrikClient,
    PolypStrikOtpRequired,
)
from .vsi import PolypStrikVsiError

__all__ = [
    "PolypStrikAPIError",
    "PolypStrikAuthError",
    "PolypStrikClient",
    "PolypStrikOtpRequired",
    "PolypStrikVsiError",
    "annotate_with_polypstrik",
]
