"""Install-check of the built zip in headless QGIS, isolated from the repository code.

Run with the QGIS Python interpreter from outside the repository and without PYTHONPATH
(the check fails if the package is not loaded from the zip), e.g. on macOS:
    cd /tmp && /Applications/QGIS.app/Contents/MacOS/python REPO/tools/check_plugin_zip_qgis.py REPO/dist/fao56_cwr_mapper-X.zip

Unpacks the zip into a temporary plugins folder, loads the plugin as QGIS does
(classFactory/initGui), checks the Processing provider and runs the algorithm
on sample_data/tekirdag_fields.gpkg with constant fake weather (no network).
"""

import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fake_fetcher(url):
    q = parse_qs(urlparse(url).query)
    start = datetime.strptime(q["start"][0], "%Y%m%d").date()
    end = datetime.strptime(q["end"][0], "%Y%m%d").date()
    days = [(start + timedelta(days=k)).strftime("%Y%m%d") for k in range((end - start).days + 1)]
    weather = {"T2M_MAX": 30.0, "T2M_MIN": 18.0, "T2MDEW": 14.0, "RH2M": 55.0, "WS2M": 2.0,
               "ALLSKY_SFC_SW_DWN": 25.0, "PRECTOTCORR": 0.0}
    return json.dumps({
        "geometry": {"coordinates": [float(q["longitude"][0]), float(q["latitude"][0]), 100.0]},
        "properties": {"parameter": {p: {d: v for d in days} for p, v in weather.items()}},
        "header": {"fill_value": -999.0, "sources": ["FAKE"], "api": {"version": "test"}},
        "parameters": {"ALLSKY_SFC_SW_DWN": {"units": "MJ/m^2/day"}},
    }).encode()


class DummyIface:
    """Stand-in for QgisInterface; the plugin only stores it."""


def main(zip_path):
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    plugins_dir = tempfile.mkdtemp(prefix="qgis_plugins_")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(plugins_dir)
    sys.path.insert(0, plugins_dir)

    from qgis.core import (QgsApplication, QgsProcessingContext, QgsProcessingFeedback,
                           QgsVectorLayer)
    app = QgsApplication([], False)
    app.initQgis()

    import fao56_cwr_mapper
    check("plugin imported from the zip, not the repository",
          os.path.dirname(fao56_cwr_mapper.__file__).startswith(plugins_dir), fao56_cwr_mapper.__file__)

    plugin = fao56_cwr_mapper.classFactory(DummyIface())
    plugin.initGui()
    registry = QgsApplication.processingRegistry()
    provider = registry.providerById("fao56cwr")
    check("Processing provider registered", provider is not None)
    check("provider icon loads", provider is not None and not provider.icon().isNull())
    alg = registry.createAlgorithmById("fao56cwr:fieldcropwaterrequirement")
    check("algorithm available", alg is not None)

    from fao56_cwr_mapper.qgis_processing.field_cwr_algorithm import FieldCropWaterRequirement
    FieldCropWaterRequirement.fetcher = staticmethod(fake_fetcher)
    layer = QgsVectorLayer(os.path.join(ROOT, "sample_data", "tekirdag_fields.gpkg") + "|layername=fields",
                           "sample", "ogr")
    report = os.path.join(plugins_dir, "report.html")
    context = QgsProcessingContext()
    context.setEllipsoid("EPSG:7030")
    alg = FieldCropWaterRequirement()
    alg.initAlgorithm()
    res, ok = alg.run({"INPUT": layer, "OUTPUT": "memory:", "USE_CACHE": False,
                       "OUTPUT_REPORT": report}, context, QgsProcessingFeedback())
    check("algorithm runs on the sample layer", ok)
    out = context.getMapLayer(res["OUTPUT"]) if ok else None
    statuses = [f["status"] for f in out.getFeatures()] if out else []
    check("all sample fields computed", statuses and all(s == "ok" for s in statuses), statuses)
    check("report written", os.path.isfile(report))

    plugin.unload()
    check("provider removed on unload", registry.providerById("fao56cwr") is None)

    for name, ok, detail in checks:
        print("{}  {}{}".format("PASS" if ok else "FAIL", name, "" if ok or not detail else "  ({})".format(detail)))
    failed = [c for c in checks if not c[1]]
    print("OK" if not failed else "FAILED ({})".format(len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
