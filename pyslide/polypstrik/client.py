# -*- coding: utf-8 -*-

import os


__all__ = [
    "PolypStrikAPIError",
    "PolypStrikAuthError",
    "PolypStrikOtpRequired",
    "PolypStrikClient",
]


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


class PolypStrikClient:
    def __init__(self, base_url=None, timeout=30, verify=True):
        url = base_url or os.environ.get("POLYPSTRIK_BASE_URL")
        if not url:
            raise ValueError(
                "base_url is required (or set POLYPSTRIK_BASE_URL)"
            )
        self.base_url = url.rstrip("/")
        self.timeout = timeout
        # False (or a CA bundle path) for local Docker self-signed TLS.
        self.verify = verify

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
        """ Exchange username and password (& optional TOTP) for an API token.

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

    def create_project(self, files, token, *, pathbt_options=None, timeout=None):
        """ Upload file(s) and create a project to start analysis

        Parameters
        ----------
        files : path, file object, or sequence of those
            Input slide(s) / archives to upload as ``input_files``.
        token : str
            API token from :meth:`login`.
        pathbt_options : dict, optional
            PathBT options sent as ``pathbt_options_json``.
        timeout : float or tuple, optional
            Upload timeout; defaults to ``self.timeout``.

        Returns
        -------
        dict
            Response with ``id``, ``samples_created``, ``queue_entry_id``,
            and ``pathbt_processing_options``.
        """
        import json
        import requests

        if isinstance(files, (str, bytes, os.PathLike)):
            files = [files]

        opened = []
        multipart = []
        try:
            for f in files:
                if hasattr(f, "read"):
                    fh, name = f, getattr(f, "name", "upload.bin")
                    name = os.path.basename(name)
                else:
                    path = os.fspath(f)
                    fh = open(path, "rb")
                    opened.append(fh)
                    name = os.path.basename(path)
                # (field_name, (filename, fileobj, content_type))
                multipart.append(
                    ("input_files", (name, fh, "application/octet-stream"))
                )

            data = None
            if pathbt_options is not None:
                data = {"pathbt_options_json": json.dumps(pathbt_options)}

            # Upload may take a while for large WSIs.
            upload_timeout = timeout if timeout is not None else self.timeout

            response = requests.post(
                self._url("/api/v1/projects/"),
                headers={"Authorization": f"Token {token}"},
                files=multipart,
                data=data,
                timeout=upload_timeout,
                verify=self.verify,
            )
        finally:
            for fh in opened:
                fh.close()

        if response.status_code == 201:
            return response.json()

        self._raise_for_error(response, "Create project")

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

        response = requests.get(
            self._url(f"/api/v1/projects/{project_id}/status/"),
            headers={"Authorization": f"Token {token}"},
            timeout=self.timeout,
            verify=self.verify,
        )

        if response.status_code == 200:
            return response.json()

        self._raise_for_error(response, "Get status")

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
            sample carries ``pathbt_outputs`` and ``download_urls``.
        """
        import requests

        response = requests.get(
            self._url(f"/api/v1/projects/{project_id}/"),
            headers={"Authorization": f"Token {token}"},
            timeout=self.timeout,
            verify=self.verify,
        )

        if response.status_code == 200:
            return response.json()

        self._raise_for_error(response, "Get project")

    def download_sample_file(
        self, sample_id, file_field, token, dest_path, *, timeout=None
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

        Returns
        -------
        str
            Path of the written file (same as ``dest_path``).
        """
        import requests

        dest_path = os.fspath(dest_path)
        parent = os.path.dirname(os.path.abspath(dest_path))
        os.makedirs(parent, exist_ok=True)

        # Stream the large artifacts (feature tensors, patch zips, etc.)
        download_timeout = timeout if timeout is not None else self.timeout

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

            # Write to a partial file first to avoid a truncated file that looks complete
            part_path = dest_path + ".part"
            try:
                with open(part_path, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            fh.write(chunk)
                os.replace(part_path, dest_path)
            except BaseException:
                if os.path.exists(part_path):
                    os.remove(part_path)
                raise

        return dest_path
