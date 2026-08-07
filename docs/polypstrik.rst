PolypStrik
==========

Optional remote-annotation client for the PolypStrik (strik) REST API.
Install the optional dependency first::

    pip install -e ".[polypstrik]"

This subpackage does **not** analyze slides locally. It uploads a slide once,
polls analysis status on the server, and downloads PathBT outputs when complete.

One-time setup
--------------
Save server defaults so you do not need ``--base-url`` / ``--no-verify`` every
time (stored in ``~/.polypstrik/config.json``)::

    python -m pyslide.polypstrik configure --base-url https://localhost --no-verify --timeout 7200

After the first successful login, the API token is saved under
``~/.polypstrik/credentials.json`` (password is not required on later runs).

Environment / config
--------------------

Resolution order for connection settings: CLI flag, then environment variable,
then ``~/.polypstrik/config.json``.

* ``POLYPSTRIK_BASE_URL`` — server base URL
* ``POLYPSTRIK_USER`` / ``POLYPSTRIK_PASSWORD`` / ``POLYPSTRIK_OTP`` — login (first time)
* ``POLYPSTRIK_VERIFY=0`` — disable TLS verify for local self-signed Docker
* ``~/.polypstrik/jobs.json`` — slide path to ``project_id`` registry (avoids re-upload)

CLI
---
After ``configure``, typical usage::

    python -m pyslide.polypstrik annotate path/to/slide.tif
    python -m pyslide.polypstrik annotate --wait path/to/slide.tif
    python -m pyslide.polypstrik status path/to/slide.tif

Olympus ``.vsi``
----------------
``.vsi`` files are auto-zipped with their companion folder before upload.
Accepted companion names next to ``S19-28250 B1.vsi``:

* ``_S19-28250 B1_/`` (common Olympus export layout)
* ``S19-28250 B1_/`` (OpenSlide-style ``{stem}_``)

A clear error is raised if neither folder is present (or it is empty).

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
    ):
        """ Upload a slide once (if needed), poll status, and download results.
        """
