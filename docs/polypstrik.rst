PolypStrik
==========

Optional remote-annotation client for the PolypStrik (strik) REST API.
Install the optional dependency first::

    pip install -e ".[polypstrik]"

This subpackage does **not** analyze slides locally. It uploads a slide once,
polls analysis status on the server, and downloads PathBT outputs when complete.

Environment
-----------

* ``POLYPSTRIK_BASE_URL`` — server base URL (required unless passed explicitly)
* ``POLYPSTRIK_USER`` / ``POLYPSTRIK_PASSWORD`` / ``POLYPSTRIK_OTP`` — login
* ``POLYPSTRIK_VERIFY=0`` — disable TLS verify for local self-signed Docker
* Credentials and job registry are stored under ``~/.polypstrik/``

CLI
---
::

    python -m pyslide.polypstrik --base-url https://localhost --no-verify annotate path/to/slide.tif
    python -m pyslide.polypstrik --base-url https://localhost --no-verify annotate --wait path/to/slide.tif
    python -m pyslide.polypstrik --base-url https://localhost --no-verify status path/to/slide.tif

Olympus ``.vsi`` files are auto-zipped with their companion ``{stem}_/`` folder
before upload. A clear error is raised if that folder is missing.

Python API
----------
::

    from pyslide.polypstrik import annotate_with_polypstrik

    result = annotate_with_polypstrik(
        "path/to/slide.tif",
        base_url="https://localhost",
        verify=False,
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
        verify=True,
        upload=True,
    ):
        """ Upload a slide once (if needed), poll status, and download results.
        """
