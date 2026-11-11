"""Network access through QGIS, so the user's proxy and SSL settings apply."""

import os

from qgis.core import QgsApplication, QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from ..climate_sources.nasa_power import PowerError
from .compat import NETWORK_NO_ERROR


def qgis_fetcher(url):
    """Fetcher for nasa_power.fetch and open_meteo.fetch using QgsBlockingNetworkRequest.

    Returns the body for HTTP 200 and for the JSON error bodies of HTTP 422
    (NASA POWER) and 400 (Open-Meteo), turned into readable messages by the parsers.
    """
    request = QgsBlockingNetworkRequest()
    error = request.get(QNetworkRequest(QUrl(url)), forceRefresh=True)
    reply = request.reply()
    status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
    if error != NETWORK_NO_ERROR and status not in (400, 422):
        raise PowerError("POWER request failed: {}".format(request.errorMessage()))
    return bytes(reply.content())


def cache_dir():
    """Plugin cache folder inside the QGIS profile."""
    return os.path.join(QgsApplication.qgisSettingsDirPath(), "cache", "fao56_cwr_mapper")
