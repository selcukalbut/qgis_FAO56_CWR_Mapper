"""NASA POWER fetcher for scripts that run outside QGIS (not part of the plugin).

The plugin downloads through QGIS (fao56_cwr_mapper/qgis_processing/network.py).
Usage: nasa_power.fetch(..., fetcher=power_urllib.fetcher)
"""

import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fao56_cwr_mapper.climate_sources.nasa_power import BASE_URL, PowerError  # noqa: E402


def fetcher(url, timeout=60):
    """Body for HTTP 200 and 422 (POWER's JSON error). Only the POWER API URL is allowed."""
    if not url.startswith(BASE_URL + "?"):
        raise PowerError("Refusing to open a URL outside the NASA POWER API: " + url)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310 - https POWER URL checked above
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            return exc.read()
        raise PowerError("POWER API HTTP error {}".format(exc.code)) from exc
    except urllib.error.URLError as exc:
        raise PowerError("Cannot reach POWER API: {}".format(exc.reason)) from exc
