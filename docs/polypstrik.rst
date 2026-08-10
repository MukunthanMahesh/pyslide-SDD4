PolypStrik
==========

Optional remote-annotation client for the PolypStrik (strik) REST API.
Install the optional dependency first::

    pip install -e ".[polypstrik]"

This subpackage does not analyze slides locally. It uploads a slide once,
polls analysis status on the server, and downloads PathBT outputs when complete.

One-time setup
--------------
Save server defaults so you do not need ``--base-url`` or ``--no-verify`` every
time (stored in ``~/.polypstrik/config.json``)::

    python -m pyslide.polypstrik configure --base-url https://localhost --no-verify --timeout 7200

After the first successful login, the API token is saved under
``~/.polypstrik/credentials.json`` (password is not required on later runs).

Environment and config
----------------------

Connection settings resolve in this order: CLI flag, then environment variable,
then ``~/.polypstrik/config.json``.

* ``POLYPSTRIK_BASE_URL``: server base URL
* ``POLYPSTRIK_USER`` / ``POLYPSTRIK_PASSWORD`` / ``POLYPSTRIK_OTP``: login (first time)
* ``POLYPSTRIK_VERIFY=0``: disable TLS verify for local self-signed Docker
* ``~/.polypstrik/jobs.json``: maps slide path to ``project_id`` (avoids re-upload)

CLI
---
After ``configure``, typical usage::

    python -m pyslide.polypstrik annotate path/to/slide.tif
    python -m pyslide.polypstrik annotate --wait path/to/slide.tif
    python -m pyslide.polypstrik status path/to/slide.tif

On a terminal, the client shows upload and download progress bars. With
``--wait``, it also shows a processing bar (an indeterminate spinner unless the
server reports a percentage). Transient network errors are retried a few
times with backoff. When ``verify`` is disabled (``configure --no-verify``),
TLS ``InsecureRequestWarning`` is suppressed. Use ``--quiet`` to hide
progress, or ``--json`` for machine-readable output (that also disables
progress)::

    python -m pyslide.polypstrik annotate --wait path/to/slide.tif
    python -m pyslide.polypstrik --quiet annotate path/to/slide.tif
    python -m pyslide.polypstrik --json status path/to/slide.tif

Olympus ``.vsi``
----------------
``.vsi`` files are auto-zipped with their companion folder before upload.
Accepted companion names next to ``S19-28250 B1.vsi``:

* ``_S19-28250 B1_/`` (common Olympus export layout)
* ``S19-28250 B1_/`` (OpenSlide-style ``{stem}_``)

Raises an error if neither folder is present, or if the folder is empty.

Python API
----------
::

    from pyslide.polypstrik import annotate_with_polypstrik

    result = annotate_with_polypstrik(
        "path/to/slide.tif",
        wait=False,
    )
    print(result["project_id"], result["status"], result["paths"])

annotate_with_polypstrik
------------------------
::

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
        progress=None,
    ):
        """ Upload a slide once (if needed), poll status, and download results.

        ``progress`` is ``None`` (auto on TTY), ``True``, or ``False``.
        """
