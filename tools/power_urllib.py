"""NASA POWER / Open-Meteo fetcher for scripts that run outside QGIS (not part of the plugin).

The plugin downloads through QGIS (fao56_cwr_mapper/qgis_processing/network.py).
Usage: nasa_power.fetch(..., fetcher=power_urllib.fetcher)
       open_meteo.fetch(..., fetcher=power_urllib.fetcher)
"""

import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fao56_cwr_mapper.climate_sources import open_meteo  # noqa: E402
from fao56_cwr_mapper.climate_sources.nasa_power import BASE_URL, PowerError  # noqa: E402

ALLOWED = (BASE_URL + "?", open_meteo.BASE_URL + "?")
ERROR_STATUS = (400, 422)    # JSON error bodies of Open-Meteo and POWER


def fetcher(url, timeout=60):
    """Body for HTTP 200 and the JSON error statuses. Only the two API URLs are allowed."""
    if not url.startswith(ALLOWED):
        raise PowerError("Refusing to open a URL outside the NASA POWER / Open-Meteo APIs: " + url)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310 - https API URL checked above
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in ERROR_STATUS:
            return exc.read()
        raise PowerError("API HTTP error {}".format(exc.code)) from exc
    except urllib.error.URLError as exc:
        raise PowerError("Cannot reach API: {}".format(exc.reason)) from exc
