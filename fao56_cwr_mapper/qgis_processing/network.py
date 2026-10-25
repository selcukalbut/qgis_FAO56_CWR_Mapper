"""Network access through QGIS, so the user's proxy and SSL settings apply."""

import os

from qgis.core import QgsApplication, QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from ..climate_sources.nasa_power import PowerError


def qgis_fetcher(url):
    """Fetcher for nasa_power.fetch using QgsBlockingNetworkRequest.

    Returns the body for HTTP 200 and for HTTP 422 (POWER's JSON error body,
    turned into a readable message by the parser).
    """
    request = QgsBlockingNetworkRequest()
    error = request.get(QNetworkRequest(QUrl(url)), forceRefresh=True)
    reply = request.reply()
    status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
    if error != QgsBlockingNetworkRequest.NoError and status != 422:
        raise PowerError("POWER request failed: {}".format(request.errorMessage()))
    return bytes(reply.content())


def cache_dir():
    """Plugin cache folder inside the QGIS profile."""
    return os.path.join(QgsApplication.qgisSettingsDirPath(), "cache", "fao56_cwr_mapper")
