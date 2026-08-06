# -*- coding: utf-8 -*-
""" Mocked unit tests for the optional PolypStrik client."""

from __future__ import annotations

import json
import os
import sys
import zipfile
from os.path import abspath as opa
from os.path import dirname as opd
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

TEST_PATH = opa(opd(opd(__file__)))
PRJ_PATH = opd(TEST_PATH)
sys.path.insert(0, PRJ_PATH)


@pytest.fixture
def polypstrik_home(tmp_path, monkeypatch):
    """ Isolate credentials / jobs JSON under a temp directory."""
    cred = tmp_path / "credentials.json"
    jobs = tmp_path / "jobs.json"
    monkeypatch.setenv("POLYPSTRIK_CREDENTIALS", str(cred))
    monkeypatch.setenv("POLYPSTRIK_JOBS", str(jobs))
    monkeypatch.setenv("POLYPSTRIK_BASE_URL", "https://example.test")
    monkeypatch.setenv("POLYPSTRIK_USER", "admin")
    monkeypatch.setenv("POLYPSTRIK_PASSWORD", "secret")
    monkeypatch.delenv("POLYPSTRIK_OTP", raising=False)
    return tmp_path


@pytest.fixture
def tiny_slide(tmp_path):
    """ Tiny dummy file used as a multipart upload stand-in."""
    path = tmp_path / "slide.tif"
    path.write_bytes(b"tiny-slide-bytes")
    return path


def test_login_stores_token(polypstrik_home):
    from pyslide.polypstrik import auth

    client = MagicMock()
    client.login.return_value = {
        "token": "tok-abc",
        "username": "admin",
        "user_id": 1,
    }

    token = auth.ensure_credentials(client, force_login=True, verify=False)
    assert token == "tok-abc"
    assert auth.load_token() == "tok-abc"
    saved = json.loads(
        Path(os.environ["POLYPSTRIK_CREDENTIALS"]).read_text(encoding="utf-8")
    )
    assert saved["token"] == "tok-abc"
    assert saved["username"] == "admin"
    client.login.assert_called_once()


def test_otp_required_path(polypstrik_home, monkeypatch):
    from pyslide.polypstrik import auth
    from pyslide.polypstrik.client import PolypStrikOtpRequired

    client = MagicMock()
    client.login.side_effect = [
        PolypStrikOtpRequired("OTP required", status_code=400, detail="otp_required"),
        {
            "token": "tok-otp",
            "username": "admin",
            "user_id": 2,
        },
    ]
    monkeypatch.setattr(auth, "_prompt", lambda prompt, secret=False: "123456")

    token = auth.ensure_credentials(client, force_login=True, verify=False)
    assert token == "tok-otp"
    assert auth.load_token() == "tok-otp"
    assert client.login.call_count == 2
    second = client.login.call_args_list[1]
    assert second.kwargs.get("otp") == "123456" or (
        len(second.args) >= 3 and second.args[2] == "123456"
    )


def test_annotate_first_upload_saves_job(polypstrik_home, tiny_slide):
    from pyslide.polypstrik import annotate as ann
    from pyslide.polypstrik import jobs

    client = MagicMock()
    client.verify = False
    client.login.return_value = {
        "token": "tok",
        "username": "admin",
        "user_id": 1,
    }
    client.create_project.return_value = {"id": 42}
    client.get_status.return_value = {
        "project_id": 42,
        "status": "pending",
    }

    with patch.object(ann, "PolypStrikClient", return_value=client):
        result = ann.annotate_with_polypstrik(tiny_slide, verify=False)

    assert result["uploaded"] is True
    assert result["project_id"] == 42
    assert result["status"] == "pending"
    assert jobs.get_project_id(jobs.image_key(tiny_slide)) == 42
    client.create_project.assert_called_once()


def test_annotate_second_call_skips_upload(polypstrik_home, tiny_slide):
    from pyslide.polypstrik import annotate as ann

    client = MagicMock()
    client.verify = False
    client.login.return_value = {
        "token": "tok",
        "username": "admin",
        "user_id": 1,
    }
    client.create_project.return_value = {"id": 42}
    client.get_status.return_value = {
        "project_id": 42,
        "status": "processing",
    }

    with patch.object(ann, "PolypStrikClient", return_value=client):
        first = ann.annotate_with_polypstrik(tiny_slide, verify=False)
        second = ann.annotate_with_polypstrik(tiny_slide, verify=False)

    assert first["uploaded"] is True
    assert second["uploaded"] is False
    assert second["project_id"] == first["project_id"]
    assert client.create_project.call_count == 1
    assert client.get_status.call_count >= 2


def test_annotate_completed_writes_files(polypstrik_home, tiny_slide, tmp_path):
    from pyslide.polypstrik import annotate as ann

    client = MagicMock()
    client.verify = False
    client.login.return_value = {
        "token": "tok",
        "username": "admin",
        "user_id": 1,
    }
    client.create_project.return_value = {"id": 7}
    client.get_status.return_value = {
        "project_id": 7,
        "status": "completed",
    }
    client.get_project.return_value = {
        "samples": [
            {
                "id": 9,
                "pathbt_outputs": [
                    {
                        "field": "output_pathbt_mask_png",
                        "filename": "mask.png",
                    }
                ],
            }
        ]
    }

    def _download(sample_id, field, token, dest_path, timeout=None):
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"png-bytes")
        return str(dest)

    client.download_sample_file.side_effect = _download
    results = tmp_path / "out"

    with patch.object(ann, "PolypStrikClient", return_value=client):
        result = ann.annotate_with_polypstrik(
            tiny_slide, verify=False, results_dir=results
        )

    assert result["status"] == "completed"
    assert len(result["paths"]) == 1
    written = Path(result["paths"][0])
    assert written.is_file()
    assert written.read_bytes() == b"png-bytes"


def test_client_create_project_multipart_shape(tiny_slide, monkeypatch):
    requests = pytest.importorskip("requests")
    from pyslide.polypstrik.client import PolypStrikClient

    captured = {}

    class FakeResponse:
        status_code = 201

        @staticmethod
        def json():
            return {"id": 1, "samples_created": 1, "queue_entry_id": 1}

    def fake_post(url, headers=None, files=None, data=None, timeout=None, verify=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["files"] = files
        captured["data"] = data
        return FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    client = PolypStrikClient(base_url="https://example.test", verify=False)
    body = client.create_project(tiny_slide, "tok-xyz", timeout=30)

    assert body["id"] == 1
    assert captured["url"].endswith("/api/v1/projects/")
    assert captured["headers"]["Authorization"] == "Token tok-xyz"
    assert len(captured["files"]) == 1
    field_name, file_tuple = captured["files"][0]
    assert field_name == "input_files"
    assert file_tuple[0] == "slide.tif"


def test_vsi_missing_companion_raises(tmp_path):
    from pyslide.polypstrik.vsi import PolypStrikVsiError, require_vsi_companion

    vsi = tmp_path / "case.vsi"
    vsi.write_bytes(b"vsi")
    with pytest.raises(PolypStrikVsiError, match="companion"):
        require_vsi_companion(vsi)


def test_vsi_prepare_upload_zips_package(tmp_path):
    from pyslide.polypstrik.vsi import prepare_upload_path

    vsi = tmp_path / "case.vsi"
    vsi.write_bytes(b"vsi")
    companion = tmp_path / "case_"
    companion.mkdir()
    (companion / "tile.bin").write_bytes(b"tile")

    upload, cleanup = prepare_upload_path(vsi)
    try:
        assert upload.suffix == ".zip"
        with zipfile.ZipFile(upload) as zf:
            names = set(zf.namelist())
        assert "case.vsi" in names
        assert "case_/tile.bin" in names
    finally:
        for path in cleanup:
            path.unlink(missing_ok=True)
