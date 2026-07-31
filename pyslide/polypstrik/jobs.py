# -*- coding: utf-8 -*-
""" Local registry mapping slide identity → PolypStrik project_id."""

from __future__ import annotations

import json
import os
from pathlib import Path


__all__ = [
    "JOBS_PATH",
    "get_project_id",
    "image_key",
    "load_jobs",
    "save_jobs",
    "set_project_id",
]

JOBS_PATH = Path.home() / ".polypstrik" / "jobs.json"


def _path():
    """ Resolved jobs path."""
    override = os.environ.get("POLYPSTRIK_JOBS")
    if override:
        return Path(override)
    return JOBS_PATH


def image_key(path):
    """ Stable-enough identity for a local slide file.

    Uses absolute path + size + mtime (nanoseconds when available).
    """
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"No such file: {p}")
    st = p.stat()
    mtime = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
    return f"{p}|{st.st_size}|{mtime}"


def load_jobs():
    """ Return the jobs registry dict (``image_key`` → ``project_id``)."""
    path = _path()
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Allow a wrapped form {"jobs": {...}} without breaking flat files.
    if "jobs" in data and isinstance(data["jobs"], dict) and set(data) <= {
        "jobs",
        "version",
    }:
        return dict(data["jobs"])
    return {str(k): v for k, v in data.items()}


def save_jobs(jobs):
    """ Persist the jobs registry dict."""
    if not isinstance(jobs, dict):
        raise TypeError("jobs must be a dict")
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(jobs, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def get_project_id(key):
    """ Return the stored ``project_id`` for ``key``, or ``None``."""
    jobs = load_jobs()
    value = jobs.get(key)
    if value is None:
        return None
    return value


def set_project_id(key, project_id):
    """ Record ``project_id`` for ``key`` and save the registry.

    Returns
    -------
    project_id
        The value that was stored.
    """
    if not key:
        raise ValueError("key must be a non-empty string")
    if project_id is None:
        raise ValueError("project_id is required")
    jobs = load_jobs()
    jobs[str(key)] = project_id
    save_jobs(jobs)
    return project_id
