# -*- coding: utf-8 -*-
""" Optional client for PolypStrik remote annotation."""

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
