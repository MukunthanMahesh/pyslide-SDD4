# -*- coding: utf-8 -*-
""" Olympus ``.vsi`` companion-folder checks and upload packaging."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path


__all__ = [
    "PolypStrikVsiError",
    "companion_dir",
    "prepare_upload_path",
    "require_vsi_companion",
    "zip_vsi_package",
]


class PolypStrikVsiError(ValueError):
    """ Olympus ``.vsi`` package is incomplete or invalid for upload."""


def companion_dir(vsi_path):
    """ Return the expected Olympus companion directory for a ``.vsi`` file.

    For ``slide.vsi`` this is ``slide_/`` next to the file.
    """
    vsi = Path(vsi_path).resolve()
    return vsi.parent / f"{vsi.stem}_"


def require_vsi_companion(vsi_path):
    """ Return the companion directory, or raise if it is missing / empty.

    Parameters
    ----------
    vsi_path : str or path-like
        Path to a ``.vsi`` file.

    Returns
    -------
    pathlib.Path
        Absolute path to the companion ``{stem}_/`` directory.

    Raises
    ------
    PolypStrikVsiError
        Companion folder is missing or contains no files.
    """
    vsi = Path(vsi_path).resolve()
    if vsi.suffix.lower() != ".vsi":
        raise PolypStrikVsiError(f"Not a .vsi file: {vsi}")

    companion = companion_dir(vsi)
    if not companion.is_dir():
        raise PolypStrikVsiError(
            f"Olympus .vsi requires companion folder '{companion.name}/' "
            f"next to the slide.\n"
            f"  slide:      {vsi}\n"
            f"  expected:   {companion}\n"
            f"Zip the .vsi with that folder, or place '{companion.name}/' "
            f"beside the file and retry."
        )

    # Ensure the folder is not an empty placeholder.
    has_file = False
    for _root, _dirs, files in os.walk(companion):
        if files:
            has_file = True
            break
    if not has_file:
        raise PolypStrikVsiError(
            f"Companion folder is empty: {companion}\n"
            f"OpenSlide / PathBT need the pyramid data inside "
            f"'{companion.name}/'."
        )
    return companion


def zip_vsi_package(vsi_path, dest_zip=None):
    """ Zip a ``.vsi`` file with its companion ``{stem}_/`` folder.

    Archive layout (zip root)::

        slide.vsi
        slide_/...

    Uses ``ZIP_STORED`` so large WSI payloads are not re-compressed.

    Parameters
    ----------
    vsi_path : str or path-like
        Path to the ``.vsi`` file.
    dest_zip : str or path-like, optional
        Destination zip path. When omitted, a temp file is created.

    Returns
    -------
    pathlib.Path
        Path to the written zip archive.
    """
    vsi = Path(vsi_path).resolve()
    companion = require_vsi_companion(vsi)
    parent = vsi.parent

    if dest_zip is None:
        fd, name = tempfile.mkstemp(prefix=f"{vsi.stem}_", suffix=".zip")
        os.close(fd)
        dest = Path(name)
    else:
        dest = Path(dest_zip)
        dest.parent.mkdir(parents=True, exist_ok=True)

    # Store (no deflate): companion tiles / pyramids are large and often
    # already compressed; re-zipping would waste CPU on multi-GB slides.
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.write(vsi, arcname=vsi.name)
        for root, _dirs, files in os.walk(companion):
            for name in files:
                full = Path(root) / name
                arcname = full.relative_to(parent).as_posix()
                zf.write(full, arcname=arcname)

    return dest


def prepare_upload_path(image_path):
    """ Resolve the path that should be uploaded for ``image_path``.

    Non-``.vsi`` paths are returned unchanged. ``.vsi`` paths are checked for
    a companion folder and packaged into a temporary zip.

    Parameters
    ----------
    image_path : str or path-like
        Local slide / archive path.

    Returns
    -------
    upload_path : pathlib.Path
        File to pass to ``create_project``.
    cleanup_paths : list of pathlib.Path
        Temporary files the caller should delete after upload.
    """
    path = Path(image_path).resolve()
    if path.suffix.lower() != ".vsi":
        return path, []

    zip_path = zip_vsi_package(path)
    return zip_path, [zip_path]
