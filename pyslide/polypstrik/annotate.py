# -*- coding: utf-8 -*-
""" High-level PolypStrik annotate flow (auth, upload once, poll, download)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from .auth import clear_token, ensure_credentials
from .client import PolypStrikAPIError, PolypStrikAuthError, PolypStrikClient
from .config import load_config, resolve_base_url, resolve_verify
from .jobs import clear_project_id, get_project_id, image_key, set_project_id
from .vsi import prepare_upload_path


__all__ = ["annotate_with_polypstrik"]

_TERMINAL = frozenset({"completed", "failed"})


def _default_results_dir(project_id, results_dir=None):
    """ Resolve ``./polypstrik_results/<project_id>/`` or ``results_dir/<project_id>/``."""
    if results_dir is not None:
        base = Path(results_dir)
    else:
        base = Path.cwd() / "polypstrik_results"
    return base / str(project_id)


def _output_fields(sample):
    """ Yield ``(file_field, filename)`` for downloadable PathBT outputs."""
    seen = set()
    outputs = sample.get("pathbt_outputs") or []
    for row in outputs:
        if isinstance(row, dict):
            field = row.get("field")
            if not field:
                continue
            name = row.get("filename") or field
        elif isinstance(row, str):
            field, name = row, row
        else:
            continue
        if field in seen:
            continue
        seen.add(field)
        yield field, os.path.basename(str(name)) or field

    if seen:
        return

    for field in sample.get("download_urls") or {}:
        if not str(field).startswith("output_"):
            continue
        if field in seen:
            continue
        seen.add(field)
        yield field, field


def _download_outputs(client, project, token, dest_dir, *, timeout=None):
    """ Download available PathBT outputs; return list of local paths written."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for sample in project.get("samples") or []:
        sample_id = sample.get("id")
        if sample_id is None:
            continue
        for field, filename in _output_fields(sample):
            dest = dest_dir / f"sample_{sample_id}_{filename}"
            try:
                written = client.download_sample_file(
                    sample_id, field, token, dest, timeout=timeout
                )
            except PolypStrikAPIError:
                # Skip missing / forbidden fields; keep going for the rest.
                continue
            paths.append(str(Path(written).resolve()))
    return paths


def _call_with_reauth(client, token, fn):
    """ Call ``fn(token)``; on 401, force re-login once and retry."""
    try:
        return fn(token), token
    except PolypStrikAuthError:
        clear_token()
        token = ensure_credentials(client, force_login=True, verify=client.verify)
        return fn(token), token


def annotate_with_polypstrik(
    image_path,
    *,
    base_url=None,
    wait=False,
    poll_interval=5.0,
    timeout=None,
    results_dir=None,
    verify=None,
    upload=True,
):
    """ Upload a slide once (if needed), poll status, and download results.

    Parameters
    ----------
    image_path : str or path-like
        Local slide / archive to annotate. Olympus ``.vsi`` files are
        auto-zipped with their companion ``{stem}_/`` folder before upload.
    base_url : str, optional
        PolypStrik base URL (else env / ``~/.polypstrik/config.json``).
    wait : bool
        If True, poll until ``completed`` or ``failed``. Default False:
        check once and return.
    poll_interval : float
        Seconds between status polls when ``wait`` is True.
    timeout : float or tuple, optional
        Passed to the HTTP client for upload / download / requests.
        Falls back to ``timeout`` in ``~/.polypstrik/config.json`` when set.
    results_dir : str or path-like, optional
        Parent directory for downloads. Defaults to
        ``./polypstrik_results/<project_id>/``.
    verify : bool or str, optional
        TLS verify flag / CA path. When omitted, uses env
        ``POLYPSTRIK_VERIFY`` or saved config (``configure --no-verify``).
    upload : bool
        If False, never create a project — only look up an existing job
        (used by the ``status`` CLI). Default True.

    Returns
    -------
    dict
        Keys ``project_id``, ``status``, ``uploaded``, ``paths``,
        ``results_dir``, and raw ``status_payload``. When ``upload`` is
        False and no job exists, also includes ``message``.

    Raises
    ------
    FileNotFoundError
        ``image_path`` does not exist.
    PolypStrikVsiError
        ``.vsi`` companion folder is missing or empty (on upload).
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path.resolve()}")

    verify = resolve_verify(verify)
    if timeout is None:
        cfg_timeout = load_config().get("timeout")
        if cfg_timeout is not None:
            timeout = cfg_timeout
    client_kwargs = {
        "base_url": resolve_base_url(base_url),
        "verify": verify,
    }
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    client = PolypStrikClient(**client_kwargs)

    token = ensure_credentials(client, verify=verify)
    # Job identity stays on the original slide path (not a temp zip).
    key = image_key(path)
    project_id = get_project_id(key)
    uploaded = False
    cleanup_paths = []

    try:
        if project_id is None:
            if not upload:
                return {
                    "project_id": None,
                    "status": None,
                    "uploaded": False,
                    "paths": [],
                    "results_dir": None,
                    "status_payload": None,
                    "message": "No saved job for this slide; run annotate first.",
                }

            upload_path, cleanup_paths = prepare_upload_path(path)

            def _create(tok):
                return client.create_project(upload_path, tok, timeout=timeout)

            created, token = _call_with_reauth(client, token, _create)
            project_id = created["id"]
            set_project_id(key, project_id)
            uploaded = True

        def _status(tok):
            return client.get_status(project_id, tok)

        try:
            status_payload, token = _call_with_reauth(client, token, _status)
        except PolypStrikAPIError as exc:
            # Stale local mapping (Docker reset / project deleted).
            if getattr(exc, "status_code", None) == 404:
                clear_project_id(key)
                if not upload:
                    return {
                        "project_id": None,
                        "status": None,
                        "uploaded": False,
                        "paths": [],
                        "results_dir": None,
                        "status_payload": None,
                        "message": (
                            f"Saved project_id={project_id} was not found on "
                            f"the server (cleared local job). Run annotate "
                            f"again to re-upload."
                        ),
                    }
                upload_path, cleanup_paths = prepare_upload_path(path)

                def _create_again(tok):
                    return client.create_project(
                        upload_path, tok, timeout=timeout
                    )

                created, token = _call_with_reauth(
                    client, token, _create_again
                )
                project_id = created["id"]
                set_project_id(key, project_id)
                uploaded = True
                status_payload, token = _call_with_reauth(
                    client, token, _status
                )
            else:
                raise

        status = (
            status_payload.get("status")
            if isinstance(status_payload, dict)
            else None
        )

        if wait and status not in _TERMINAL:
            interval = max(float(poll_interval), 0.1)
            while True:
                time.sleep(interval)
                status_payload, token = _call_with_reauth(client, token, _status)
                status = (
                    status_payload.get("status")
                    if isinstance(status_payload, dict)
                    else None
                )
                if status in _TERMINAL:
                    break

        paths = []
        out_dir = None
        if status == "completed":
            out_dir = _default_results_dir(project_id, results_dir)

            def _project(tok):
                return client.get_project(project_id, tok)

            project, token = _call_with_reauth(client, token, _project)
            paths = _download_outputs(
                client, project, token, out_dir, timeout=timeout
            )
        elif results_dir is not None:
            out_dir = _default_results_dir(project_id, results_dir)

        return {
            "project_id": project_id,
            "status": status,
            "uploaded": uploaded,
            "paths": paths,
            "results_dir": str(out_dir) if out_dir is not None else None,
            "status_payload": status_payload,
        }
    finally:
        for tmp in cleanup_paths:
            try:
                Path(tmp).unlink()
            except OSError:
                pass
