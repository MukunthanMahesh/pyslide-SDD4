pyslide - Python whole slide image analysis toolkit
============
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/9fd878feda1d4780b8c101efda3422a4)](https://app.codacy.com/app/PingjunChen/pyslide?utm_source=github.com&utm_medium=referral&utm_content=PingjunChen/pyslide&utm_campaign=Badge_Grade_Dashboard)
[![CircleCI](https://circleci.com/gh/PingjunChen/pyslide.svg?style=svg)](https://circleci.com/gh/PingjunChen/pyslide)
[![Documentation Status](https://readthedocs.org/projects/pyslide/badge/?version=latest)](https://pyslide.readthedocs.io/en/latest/?badge=latest)
![](https://img.shields.io/github/license/PingjunChen/pyslide.svg)
[![codecov](https://codecov.io/gh/PingjunChen/pyslide/branch/master/graph/badge.svg)](https://codecov.io/gh/PingjunChen/pyslide)
[![Downloads](https://pepy.tech/badge/pyslide)](https://pepy.tech/project/pyslide)
![](https://img.shields.io/github/stars/PingjunChen/pyslide.svg)

![pyslide-banner](./docs/thyroid_diag.png)

Please consider `star` this repo if you find [pyslide](https://github.com/PingjunChen/pyslide) to be helpful for your work.

Installation
------------
To install pyslide, apt dependences before pip:
```alpha
sudo apt-get install openslide-tools
sudo apt-get install libgeos-dev
pip install -r requirements.txt
pip install pyslide==0.5.0
```

Usage
------------

Documentation
------------
Hosted in [https://pyslide.readthedocs.io](https://pyslide.readthedocs.io), powered by [readthedocs](https://readthedocs.org) and [Sphinx](http://www.sphinx-doc.org).

Optional PolypStrik remote annotation
------------
Requires `pip install -e ".[polypstrik]"`:

```bash
python -m pyslide.polypstrik configure --base-url https://localhost --no-verify --timeout 7200
python -m pyslide.polypstrik annotate path/to/slide.tif
python -m pyslide.polypstrik annotate --wait path/to/slide.tif
python -m pyslide.polypstrik status path/to/slide.tif
```

On a TTY, annotate shows upload/download progress and (with `--wait`) a processing progress bar. Transient network errors are retried automatically. TLS warnings are suppressed when verify is disabled. Use `--quiet` or `--json` to hide progress.

```python
from pyslide.polypstrik import annotate_with_polypstrik

result = annotate_with_polypstrik("path/to/slide.tif", wait=True)
print(result["status"], result["paths"])
```

Olympus `.vsi` slides are auto-zipped with their companion folder (`_{stem}_/` or `{stem}_/`) before upload. See the PolypStrik docs page for details.

License
------------
[pyslide](https://github.com/PingjunChen/pyslide) is free software made available under the MIT License. For details see the [LICENSE](LICENSE) file.

Contributors
------------
See the [AUTHORS.md](AUTHORS.md) file for a complete list of contributors to the project.

Contributing
------------
``pyslide`` is an open source project and all whole slide image analysis related functions are very welcome to contribute. An easy way to get started is by suggesting a new enhancement on the [Issues](https://github.com/PingjunChen/pyslide/issues). If you have found a bug, then either report this through [Issues](https://github.com/PingjunChen/pyslide/issues), or even better, make a fork of the repository, fix the bug and then create a [Pull Request](https://github.com/PingjunChen/pyslide/pulls) to get the fix into the master branch.
