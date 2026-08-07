# -*- coding: utf-8 -*-

import os
import time


__all__ = [
    "PolypStrikAPIError",
    "PolypStrikAuthError",
    "PolypStrikOtpRequired",
    "PolypStrikClient",
]

# HTTP statuses worth retrying (transient server or gateway issues).
_RETRY_HTTP = frozenset({502, 503, 504})
_DEFAULT_RETRIES = 3
_UPLOAD_RETRIES = 2


class PolypStrikAPIError(Exception):
    """PolypStrik API request failed."""

    def __init__(self, message, *, status_code=None, detail=None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class PolypStrikAuthError(PolypStrikAPIError):
    """Authentication failed against the PolypStrik API."""


class PolypStrikOtpRequired(PolypStrikAuthError):
    """Account has 2FA enabled. Call login again with an OTP code."""


def _is_transient_exception(exc):
    """ Return True for network blips worth retrying."""
    try:
        import requests
    except ImportError:
        return False
    return isinstance(
        exc,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ),
    )


def _with_retries(fn, *, stage, retries=_DEFAULT_RETRIES, progress=False):
    """ Call ``fn()`` with exponential backoff on transient failures.

    Parameters
    ----------
    fn : callable
        Zero-arg callable that performs the request.
    stage : str
        Human label used in the final error (``upload``, ``status``, and so on).
    retries : int
        Total attempts (including the first).
    progress : bool
        If True, print retry notices to stderr.

    Returns
    -------
    result of ``fn()``
    """
    import sys

    attempts = max(int(retries), 1)
    last_exc = None
    started = time.monotonic()

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except PolypStrikAuthError:
            # Auth failures must surface immediately for re-login.
            raise
        except PolypStrikAPIError as exc:
            if getattr(exc, "status_code", None) not in _RETRY_HTTP:
                raise
            last_exc = exc
        except Exception as exc:
            if not _is_transient_exception(exc):
                raise
            last_exc = exc

        if attempt >= attempts:
            break

        delay = min(2 ** (attempt - 1), 8)
        if progress:
            sys.stderr.write(
                f"\n{stage} failed (attempt {attempt}/{attempts}): "
                f"{last_exc}; retrying in {delay}s…\n"
            )
            sys.stderr.flush()
        time.sleep(delay)

    elapsed = int(time.monotonic() - started)
    raise PolypStrikAPIError(
        f"{stage} failed after {attempts} attempt(s) "
        f"({elapsed}s elapsed): {last_exc}",
        status_code=getattr(last_exc, "status_code", None),
        detail=getattr(last_exc, "detail", None),
    )


def _suppress_insecure_warning():
    """ Hide urllib3 InsecureRequestWarning (used when verify=False)."""
    import warnings

    # Catch both the urllib3 category and the plain message text that
    # requests or urllib3 emit on some Python or package combos.
    warnings.filterwarnings("ignore", message="Unverified HTTPS request.*")
    try:
        import urllib3
        from urllib3.exceptions import InsecureRequestWarning
    except ImportError:
        return
    urllib3.disable_warnings(InsecureRequestWarning)
    warnings.filterwarnings("ignore", category=InsecureRequestWarning)
    try:
        import requests

        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    except Exception:
        pass


class PolypStrikClient:
    def __init__(self, base_url=None, timeout=30, verify=None, progress=False):
        from .config import resolve_base_url, resolve_verify

        url = resolve_base_url(base_url)
        if not url:
            raise ValueError(
                "base_url is required (pass it, set POLYPSTRIK_BASE_URL, "
                "or run: python -m pyslide.polypstrik configure "
                "--base-url https://...)"
            )
        self.base_url = url.rstrip("/")
        self.timeout = timeout
        # False (or a CA bundle path) for local Docker with self-signed TLS.
        self.verify = resolve_verify(verify)
        self.progress = bool(progress)
        if self.verify is False:
            _suppress_insecure_warning()

    def _url(self, path):
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    @staticmethod
    def _response_body(response):
        """ Parse JSON body if possible; return ``(body, detail)``."""
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        return body, body.get("detail")

    def _raise_for_error(self, response, action):
        """ Raise AuthError on 401, otherwise APIError with a clear message."""
        body, detail = self._response_body(response)

        if response.status_code == 401:
            raise PolypStrikAuthError(
                detail or response.text or "Authentication failed.",
                status_code=401,
                detail=detail,
            )

        message = detail or response.text or (
            f"{action} failed ({response.status_code})"
        )
        raise PolypStrikAPIError(
            message,
            status_code=response.status_code,
            detail=detail,
        )

    def login(self, username, password, otp=None):
        """ Exchange username and password (and optional TOTP) for an API token.

        Parameters
        ----------
        username : str
            PolypStrik account username.
        password : str
            Account password.
        otp : str, optional
            TOTP code when the account has 2FA enabled.

        Returns
        -------
        dict
            Response payload with keys ``token``, ``user_id``, ``username``.

        Raises
        ------
        PolypStrikOtpRequired
            Account has 2FA and ``otp`` was not provided.
        PolypStrikAuthError
            Invalid credentials, invalid OTP, or other auth failure.
        """
        import requests

        payload = {"username": username, "password": password}
        if otp is not None and str(otp).strip():
            payload["otp"] = str(otp).strip()

        response = requests.post(
            self._url("/api/v1/auth/login/"),
            json=payload,
            timeout=self.timeout,
            verify=self.verify,
        )

        if response.status_code == 200:
            return response.json()

        body, detail = self._response_body(response)

        if response.status_code == 400 and detail == "otp_required":
            raise PolypStrikOtpRequired(
                body.get("message")
                or "OTP required for this account.",
                status_code=400,
                detail=detail,
            )

        message = detail or response.text or (
            f"Login failed ({response.status_code})"
        )
        raise PolypStrikAuthError(
            message,
            status_code=response.status_code,
            detail=detail,
        )

    def create_project(
        self, files, token, *, pathbt_options=None, timeout=None, progress=None
    ):
        """ Upload file(s) and create a project to start analysis.

        Parameters
        ----------
        files : path, file object, or sequence of those
            Input slide(s) or archives to upload as ``input_files``.
        token : str
            API token from :meth:`login`.
        pathbt_options : dict, optional
            PathBT options sent as ``pathbt_options_json``.
        timeout : float or tuple, optional
            Upload timeout; defaults to ``self.timeout``.
        progress : bool, optional
            Show upload progress. Defaults to ``self.progress``.

        Returns
        -------
        dict
            Response with ``id``, ``samples_created``, ``queue_entry_id``,
            and ``pathbt_processing_options``.
        """
        import json
        import requests

        from .progress import ProgressFile, upload_bar

        if isinstance(files, (str, bytes, os.PathLike)):
            files = [files]
        else:
            files = list(files)

        show = self.progress if progress is None else bool(progress)
        upload_timeout = timeout if timeout is not None else self.timeout
        data = None
        if pathbt_options is not None:
            data = {"pathbt_options_json": json.dumps(pathbt_options)}

        def _attempt():
            # Only close path-based handles we opened (not caller-owned files).
            owned = []
            bars = []
            multipart = []
            try:
                for f in files:
                    if hasattr(f, "read"):
                        # Caller-owned file object: wrap in place (do not reopen).
                        name = os.path.basename(
                            getattr(f, "name", "upload.bin")
                        )
                        try:
                            f.seek(0)
                        except Exception:
                            pass
                        total = None
                        try:
                            pos = f.tell()
                            f.seek(0, os.SEEK_END)
                            total = f.tell()
                            f.seek(pos)
                        except Exception:
                            total = None
                        bar = upload_bar(name, total, enabled=show)
                        bars.append(bar)
                        fh = ProgressFile(f, bar)
                    else:
                        path = os.fspath(f)
                        name = os.path.basename(path)
                        total = os.path.getsize(path)
                        raw = open(path, "rb")
                        bar = upload_bar(name, total, enabled=show)
                        bars.append(bar)
                        fh = ProgressFile(raw, bar)
                        owned.append(fh)

                    multipart.append(
                        (
                            "input_files",
                            (name, fh, "application/octet-stream"),
                        )
                    )

                response = requests.post(
                    self._url("/api/v1/projects/"),
                    headers={"Authorization": f"Token {token}"},
                    files=multipart,
                    data=data,
                    timeout=upload_timeout,
                    verify=self.verify,
                )
            finally:
                for bar in bars:
                    try:
                        bar.close()
                    except Exception:
                        pass
                for fh in owned:
                    try:
                        fh.close()
                    except Exception:
                        pass

            if response.status_code == 201:
                return response.json()

            self._raise_for_error(response, "Create project")

        return _with_retries(
            _attempt,
            stage="upload",
            retries=_UPLOAD_RETRIES,
            progress=show,
        )

    def get_status(self, project_id, token):
        """ Poll analysis status for a project.

        Parameters
        ----------
        project_id : int
            Project id returned by :meth:`create_project` (response key ``id``).
        token : str
            API token from :meth:`login`.

        Returns
        -------
        dict
            Payload with ``project_id``, ``status``, timestamps, and ``queue_id``.
            ``status`` is one of ``pending``, ``processing``, ``completed``,
            ``failed``, or ``None`` if no queue exists yet.
        """
        import requests

        def _attempt():
            response = requests.get(
                self._url(f"/api/v1/projects/{project_id}/status/"),
                headers={"Authorization": f"Token {token}"},
                timeout=self.timeout,
                verify=self.verify,
            )

            if response.status_code == 200:
                return response.json()

            self._raise_for_error(response, "Get status")

        return _with_retries(
            _attempt,
            stage="status",
            retries=_DEFAULT_RETRIES,
            progress=self.progress,
        )

    def get_project(self, project_id, token):
        """ Fetch project detail with sample outputs and download URLs.

        Parameters
        ----------
        project_id : int
            Project id returned by :meth:`create_project` (response key ``id``).
        token : str
            API token from :meth:`login`.

        Returns
        -------
        dict
            Payload with ``pathbt_processing_options``, ``analysis_busy``,
            ``queue``, ``project_files``, and ``samples`` (newest first). Each
            sample includes ``pathbt_outputs`` and ``download_urls``.
        """
        import requests

        def _attempt():
            response = requests.get(
                self._url(f"/api/v1/projects/{project_id}/"),
                headers={"Authorization": f"Token {token}"},
                timeout=self.timeout,
                verify=self.verify,
            )

            if response.status_code == 200:
                return response.json()

            self._raise_for_error(response, "Get project")

        return _with_retries(
            _attempt,
            stage="project",
            retries=_DEFAULT_RETRIES,
            progress=self.progress,
        )

    def download_sample_file(
        self,
        sample_id,
        file_field,
        token,
        dest_path,
        *,
        timeout=None,
        progress=None,
    ):
        """ Download one PathBT output file for a sample.

        Parameters
        ----------
        sample_id : int
            Sample id from ``samples`` in :meth:`get_project`.
        file_field : str
            Sample file field to fetch, e.g. ``output_pathbt_mask_png``.
        token : str
            API token from :meth:`login`.
        dest_path : str
            Local path to write the file to. Parent directories are created.
        timeout : float or tuple, optional
            Download timeout; defaults to ``self.timeout``.
        progress : bool, optional
            Show download progress. Defaults to ``self.progress``.

        Returns
        -------
        str
            Path of the written file (same as ``dest_path``).
        """
        import requests

        from .progress import download_bar

        dest_path = os.fspath(dest_path)
        parent = os.path.dirname(os.path.abspath(dest_path))
        os.makedirs(parent, exist_ok=True)

        download_timeout = timeout if timeout is not None else self.timeout
        show = self.progress if progress is None else bool(progress)
        filename = os.path.basename(dest_path) or file_field

        def _attempt():
            with requests.get(
                self._url(
                    f"/api/v1/samples/{sample_id}/download/{file_field}/"
                ),
                headers={"Authorization": f"Token {token}"},
                timeout=download_timeout,
                verify=self.verify,
                stream=True,
            ) as response:
                if response.status_code != 200:
                    self._raise_for_error(response, "Download")

                total = None
                try:
                    total = int(response.headers.get("Content-Length") or 0)
                except (TypeError, ValueError):
                    total = None
                if not total:
                    total = None

                part_path = dest_path + ".part"
                bar = download_bar(filename, total, enabled=show)
                try:
                    with open(part_path, "wb") as fh:
                        for chunk in response.iter_content(
                            chunk_size=1024 * 1024
                        ):
                            if chunk:
                                fh.write(chunk)
                                bar.update(len(chunk))
                    os.replace(part_path, dest_path)
                except BaseException:
                    if os.path.exists(part_path):
                        os.remove(part_path)
                    raise
                finally:
                    bar.close()

            return dest_path

        return _with_retries(
            _attempt,
            stage="download",
            retries=_DEFAULT_RETRIES,
            progress=show,
        )
