# -*- coding: utf-8 -*-
""" Olympus ``.vsi`` companion folder checks and upload packaging."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path


__all__ = [
    "PolypStrikVsiError",
    "companion_candidates",
    "companion_dir",
    "prepare_upload_path",
    "require_vsi_companion",
    "zip_vsi_package",
]


class PolypStrikVsiError(ValueError):
    """ Olympus ``.vsi`` package is incomplete or invalid for upload."""


def companion_candidates(vsi_path):
    """ Return possible Olympus companion directories for a ``.vsi`` file.

    Supports both common layouts next to ``S19-28250 B1.vsi``:

    * ``S19-28250 B1_/``  (OpenSlide-style ``{stem}_``)
    * ``_S19-28250 B1_/`` (Olympus export-style ``_{stem}_``)
    """
    vsi = Path(vsi_path).resolve()
    stem = vsi.stem
    parent = vsi.parent
    # Prefer _{stem}_ first; that matches typical Olympus folder naming.
    names = [f"_{stem}_", f"{stem}_"]
    # De-dupe if stem already starts/ends with underscore.
    seen = set()
    out = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        out.append(parent / name)
    return out


def companion_dir(vsi_path):
    """ Return the preferred companion directory path (may not exist yet).

    Prefers the Olympus ``_{stem}_`` layout when listing candidates.
    """
    return companion_candidates(vsi_path)[0]


def _dir_has_files(path):
    for _root, _dirs, files in os.walk(path):
        if files:
            return True
    return False


def require_vsi_companion(vsi_path):
    """ Return the companion directory, or raise if it is missing or empty.

    Parameters
    ----------
    vsi_path : str or path-like
        Path to a ``.vsi`` file.

    Returns
    -------
    pathlib.Path
        Absolute path to the companion directory that was found.

    Raises
    ------
    PolypStrikVsiError
        No usable companion folder next to the slide.
    """
    vsi = Path(vsi_path).resolve()
    if vsi.suffix.lower() != ".vsi":
        raise PolypStrikVsiError(f"Not a .vsi file: {vsi}")

    candidates = companion_candidates(vsi)
    found_empty = []
    for companion in candidates:
        if not companion.is_dir():
            continue
        if not _dir_has_files(companion):
            found_empty.append(companion)
            continue
        return companion

    expected = "\n".join(f"  expected:   {c}" for c in candidates)
    if found_empty:
        empty = "\n".join(f"  empty:      {c}" for c in found_empty)
        raise PolypStrikVsiError(
            f"Olympus .vsi companion folder is empty.\n"
            f"  slide:      {vsi}\n"
            f"{empty}\n"
            f"OpenSlide and PathBT need the pyramid data inside the folder."
        )
    raise PolypStrikVsiError(
        f"Olympus .vsi requires a companion folder next to the slide.\n"
        f"  slide:      {vsi}\n"
        f"{expected}\n"
        f"Zip the .vsi with that folder, or place the companion beside "
        f"the file and retry."
    )


def zip_vsi_package(vsi_path, dest_zip=None):
    """ Zip a ``.vsi`` file with its companion folder.

    Archive layout keeps the real companion folder name at the zip root::

        S19-28250 B1.vsi
        _S19-28250 B1_/...

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
        fd, name = tempfile.mkstemp(prefix="vsi_", suffix=".zip")
        os.close(fd)
        dest = Path(name)
    else:
        dest = Path(dest_zip)
        dest.parent.mkdir(parents=True, exist_ok=True)

    # Store (no deflate): companion tiles and pyramids are large and often
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
        Local slide or archive path.

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
