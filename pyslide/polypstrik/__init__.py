# -*- coding: utf-8 -*-
""" Optional PolypStrik remote-annotation client."""

from .annotate import annotate_with_polypstrik
from .client import (
    PolypStrikAPIError,
    PolypStrikAuthError,
    PolypStrikClient,
    PolypStrikOtpRequired,
)

__all__ = [
    "PolypStrikAPIError",
    "PolypStrikAuthError",
    "PolypStrikClient",
    "PolypStrikOtpRequired",
    "annotate_with_polypstrik",
]
