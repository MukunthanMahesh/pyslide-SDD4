# -*- coding: utf-8 -*-
""" Persistent PolypStrik client settings (base URL, TLS verify)."""

from __future__ import annotations

import json
import os
from pathlib import Path


__all__ = [
    "CONFIG_PATH",
    "load_config",
    "resolve_base_url",
    "resolve_verify",
    "save_config",
]

CONFIG_PATH = Path.home() / ".polypstrik" / "config.json"


def _path():
    override = os.environ.get("POLYPSTRIK_CONFIG")
    if override:
        return Path(override)
    return CONFIG_PATH


def load_config():
    """ Return the config dict, or ``{}`` if missing/unreadable."""
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
    return data


def save_config(updates):
    """ Merge ``updates`` into the config file and save.

    Parameters
    ----------
    updates : dict
        Keys to set (e.g. ``base_url``, ``verify``, ``timeout``).

    Returns
    -------
    pathlib.Path
        Path of the written config file.
    """
    if not isinstance(updates, dict):
        raise TypeError("updates must be a dict")
    data = load_config()
    data.update(updates)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def resolve_base_url(base_url=None):
    """ Resolve base URL: explicit arg, then env, then config file."""
    if base_url:
        return str(base_url).rstrip("/")
    env = os.environ.get("POLYPSTRIK_BASE_URL")
    if env:
        return env.rstrip("/")
    cfg = load_config().get("base_url")
    if cfg:
        return str(cfg).rstrip("/")
    return None


def resolve_verify(verify=None):
    """ Resolve TLS verify: explicit arg, then env, then config, else True.

    Pass ``verify=None`` to use saved / env defaults. Pass ``False`` or a
    CA path to force a value.
    """
    if verify is not None:
        return verify

    env = os.environ.get("POLYPSTRIK_VERIFY")
    if env is not None:
        return env.strip().lower() not in ("0", "false", "no", "off")

    cfg = load_config()
    if "verify" in cfg:
        return bool(cfg["verify"])

    return True
