# -*- coding: utf-8 -*-
"""Local PolypStrik credential storage and interactive login."""

from __future__ import annotations

import getpass
import json
import os
import stat
from pathlib import Path


__all__ = [
    "CREDENTIALS_PATH",
    "clear_token",
    "ensure_credentials",
    "load_token",
    "save_token",
]

CREDENTIALS_PATH = Path.home() / ".polypstrik" / "credentials.json"


def _path():
    """ Resolved credentials path."""
    override = os.environ.get("POLYPSTRIK_CREDENTIALS")
    if override:
        return Path(override)
    return CREDENTIALS_PATH


def load_token():
    """ Return the saved API token, or ``None`` if missing/unreadable."""
    path = _path()
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    token = data.get("token")
    if not token or not isinstance(token, str):
        return None
    return token


def save_token(token, *, username=None, user_id=None):
    """ Write ``token`` (and optional identity) to the credentials file.

    On Unix the file mode is set to ``0600`` when possible.
    """
    if not token or not isinstance(token, str):
        raise ValueError("token must be a non-empty string")

    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {"token": token}
    if username is not None:
        data["username"] = username
    if user_id is not None:
        data["user_id"] = user_id

    # Restrict permissions when creating the file (best-effort on Windows).
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")

    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        # Windows and non-POSIX filesystems may ignore or reject mode bits.
        pass

    return path


def clear_token():
    """ Remove the saved credentials file if it exists."""
    path = _path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return None


def _prompt(prompt, *, secret=False):
    if secret:
        return getpass.getpass(prompt)
    return input(prompt)


def _read_login_inputs(*, username=None, password=None, otp=None):
    """ Resolve username, password, and otp from args, env, or interactive prompts."""
    user = username or os.environ.get("POLYPSTRIK_USER") or os.environ.get(
        "POLYPSTRIK_USERNAME"
    )
    pwd = password or os.environ.get("POLYPSTRIK_PASSWORD")
    code = otp if otp is not None else os.environ.get("POLYPSTRIK_OTP")

    if not user:
        user = _prompt("PolypStrik username: ").strip()
    if not pwd:
        pwd = _prompt("PolypStrik password: ", secret=True)
    if not user or not pwd:
        raise ValueError("username and password are required")
    return user, pwd, code


def ensure_credentials(
    client=None,
    *,
    force_login=False,
    base_url=None,
    verify=True,
    username=None,
    password=None,
    otp=None,
):
    """ Return a usable API token, prompting or logging in when needed.

    Parameters
    ----------
    client : PolypStrikClient, optional
        Existing client used for ``login``. Created from ``base_url`` or
        ``POLYPSTRIK_BASE_URL`` when omitted.
    force_login : bool
        If True, ignore any saved token and re-authenticate (for example
        after a 401).
    base_url, verify
        Passed to ``PolypStrikClient`` when ``client`` is not provided.
    username, password, otp : str, optional
        Non-interactive overrides; otherwise env ``POLYPSTRIK_USER``,
        ``POLYPSTRIK_PASSWORD``, ``POLYPSTRIK_OTP``, then prompts.

    Returns
    -------
    str
        API token.
    """
    from .client import PolypStrikClient, PolypStrikOtpRequired

    if not force_login:
        token = load_token()
        if token:
            return token

    if client is None:
        client = PolypStrikClient(base_url=base_url, verify=verify)

    user, pwd, code = _read_login_inputs(
        username=username, password=password, otp=otp
    )

    try:
        auth = client.login(user, pwd, otp=code)
    except PolypStrikOtpRequired:
        if code:
            # Caller already supplied a bad or stale OTP; re-raise.
            raise
        code = os.environ.get("POLYPSTRIK_OTP") or _prompt(
            "OTP code: "
        ).strip()
        if not code:
            raise
        auth = client.login(user, pwd, otp=code)

    token = auth["token"]
    save_token(
        token,
        username=auth.get("username", user),
        user_id=auth.get("user_id"),
    )
    return token
