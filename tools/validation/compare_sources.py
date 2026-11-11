"""Compare the three climate sources on the Tekirdag sample fields (run with the QGIS Python).

NASA POWER, Open-Meteo ERA5-Seamless and the NOAA GSOD record of the Tekirdag
synoptic station (WMO 17056) are run through the plugin's Processing algorithm
with the three effective rainfall methods, and the daily inputs are compared.

GSOD has no solar radiation: Rs is estimated with FAO-56 Eq. 50 (coastal,
kRs = 0.19). GSOD data of non-US stations are exchanged under WMO Resolution 40
and may not be passed on, so the station download, the converted CSV and the
station results stay in tools/validation/local/ (gitignored). The NASA POWER /
Open-Meteo tables go to stdout or --public.

    PYTHONPATH=/Applications/QGIS.app/Contents/Resources/qgis/python/plugins:. \\
    /Applications/QGIS.app/Contents/MacOS/python tools/validation/compare_sources.py --year 2024
"""

import argparse
import csv
import json
import os
import sys
import tempfile
import urllib.request
from collections import defaultdict
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from qgis.core import (QgsApplication, QgsFeature, QgsGeometry, QgsPointXY,  # noqa: E402
                       QgsProcessingContext, QgsProcessingFeedback, QgsVectorLayer)
from qgis.PyQt.QtCore import QDate  # noqa: E402

import power_urllib  # noqa: E402
from fao56_cwr_mapper.climate_sources import nasa_power, open_meteo, station_csv  # noqa: E402
from fao56_cwr_mapper.core import eto_series  # noqa: E402

LOCAL = os.path.join(ROOT, "tools", "validation", "local")
GSOD_URL = "https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/{}/17056099999.csv"
STATION = {"id": "17056", "lat": 40.9833333, "lon": 27.55, "elevation": 3.0}   # GSOD header
SOURCES = {0: "NASA POWER", 2: "Open-Meteo ERA5-Seamless", 1: "Station 17056 (GSOD)"}
PE_METHODS = {0: "Fixed 0.8", 1: "USDA SCS (CROPWAT)", 2: "USDA SCS (NEH 623, D = 75 mm)"}
MPS_PER_KNOT = 0.514444


def f_to_c(v):
    return (v - 32.0) * 5.0 / 9.0


def gsod_year(year):
    path = os.path.join(LOCAL, "gsod", "{}.csv".format(year))
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        url = GSOD_URL.format(year)
        with urllib.request.urlopen(url, timeout=60) as resp:  # nosec B310 - fixed https NOAA URL
            data = resp.read()
        with open(path, "wb") as fh:
            fh.write(data)
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def station_csv_file(years):
    """GSOD -> plugin station CSV (degC, m/s at 10 m, mm). Returns path and data notes."""
    out = os.path.join(LOCAL, "station_17056.csv")
    notes = defaultdict(int)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["station", "date", "tmax", "tmin", "tdew", "wind", "precip"])
        for y in years:
            for r in gsod_year(y):
                def val(name, missing):
                    v = float(r[name])
                    return None if v >= missing else v
                tmax, tmin, tdew = val("MAX", 9999), val("MIN", 9999), val("DEWP", 9999)
                wind, prcp = val("WDSP", 999), val("PRCP", 99.99)
                if r["PRCP_ATTRIBUTES"].strip() in ("H", "I"):     # incomplete / not reported
                    prcp = None
                if prcp is None:
                    notes["no_precip"] += 1
                w.writerow([STATION["id"], r["DATE"],
                            "" if tmax is None else round(f_to_c(tmax), 2),
                            "" if tmin is None else round(f_to_c(tmin), 2),
                            "" if tdew is None else round(f_to_c(tdew), 2),
                            "" if wind is None else round(wind * MPS_PER_KNOT, 2),
                            "" if prcp is None else round(prcp * 25.4, 1)])
                notes["days"] += 1
    return out, dict(notes)


def station_layer():
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=station:string&field=elevation:double",
                           "stations", "memory")
    f = QgsFeature(layer.fields())
    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(STATION["lon"], STATION["lat"])))
    f.setAttributes([STATION["id"], STATION["elevation"]])
    layer.dataProvider().addFeatures([f])
    return layer


def fields_layer(year):
    """Sample fields with the planting dates moved to the comparison year (wheat: the autumn before)."""
    src = QgsVectorLayer(os.path.join(ROOT, "sample_data", "tekirdag_fields.gpkg"), "f", "ogr")
    layer = QgsVectorLayer("Polygon?crs={}&field=name:string&field=crop:string&field=planted:date"
                           "&field=region:string".format(src.crs().authid()), "fields", "memory")
    feats = []
    for s in src.getFeatures():
        planted = s["planted"]
        shift = year - 2025
        f = QgsFeature(layer.fields())
        f.setGeometry(s.geometry())
        f.setAttributes([s["name"], s["crop"], QDate(planted.year() + shift, planted.month(), planted.day()),
                         s["region"]])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    return layer


def run(alg_cls, layer, source, pe, station_file, stations, tmp):
    alg = alg_cls()
    alg.initAlgorithm()
    params = {"INPUT": layer, "OUTPUT": "memory:", "USE_CACHE": True, "CLIMATE_SOURCE": source,
              "PE_METHOD": pe, "SOIL_STORAGE_MM": 75.0,
              "OUTPUT_DEKAD": os.path.join(tmp, "dekad_{}_{}.csv".format(source, pe))}
    if source == 1:
        params.update({"STATION_CSV": station_file, "STATION_LAYER": stations, "WIND_HEIGHT": 10.0,
                       "ESTIMATE_MISSING": True, "KRS": 1, "MAX_DISTANCE_KM": 50.0})
    context = QgsProcessingContext()
    context.setEllipsoid("EPSG:7030")
    res, ok = alg.run(params, context, QgsProcessingFeedback())
    if not ok:
        raise RuntimeError(res)
    out = context.getMapLayer(res["OUTPUT"]) or context.takeResultLayer(res["OUTPUT"])
    return {f["name"]: {k: f[k] for k in ("crop_used", "season_beg", "season_end", "ETo_mm", "P_mm",
                                           "Pe_mm", "NIR_mm", "miss_days", "elev_m", "status")}
            for f in out.getFeatures()}


def daily_inputs(year, station_file):
    """Daily climate per source at Field C (all fields lie within 500 m)."""
    lat, lon = 40.9728, 27.4941      # Field C, point on surface
    start, end = date(year - 1, 11, 1), date(year, 10, 31)
    out = {}
    pw = nasa_power.fetch(lat, lon, start, end, fetcher=power_urllib.fetcher)
    om = open_meteo.fetch(lat, lon, start, end, fetcher=power_urllib.fetcher)
    with open(station_file, encoding="utf-8") as fh:
        st = station_csv.read_station_csv(fh.read(), wind_height=10.0)[STATION["id"]]
    est = eto_series.Estimation(krs=0.19)
    for name, days, z, e in (("NASA POWER", pw.days, pw.elevation, None),
                             ("Open-Meteo ERA5-Seamless", om.days, om.elevation, None),
                             ("Station 17056 (GSOD)", [d for d in st.days if start <= d.day <= end],
                              STATION["elevation"], est)):
        rows = {r["day"]: r for r in eto_series.daily_eto_series(days, lat, z, estimation=e)}
        recs = []
        for d in days:
            rs, _ = eto_series.solar_radiation(d, lat, e or eto_series.Estimation(radiation=False))
            recs.append({"day": d.day, "tmax": d.tmax, "tmin": d.tmin, "tdew": d.tdew, "u2": d.u2,
                         "rs": rs, "P": d.precip, "ETo": rows[d.day]["ETo"]})
        out[name] = {"elevation": z, "days": recs}
    return out


def monthly(inputs, months):
    table = {}
    for name, src in inputs.items():
        for m in months:
            rows = [r for r in src["days"] if (r["day"].year, r["day"].month) == m]
            agg = {}
            for k in ("tmax", "tmin", "tdew", "u2", "rs"):
                v = [r[k] for r in rows if r[k] is not None]
                agg[k] = sum(v) / len(v) if v else None
            for k in ("P", "ETo"):
                v = [r[k] for r in rows if r[k] is not None]
                agg[k] = sum(v) if v else None
                agg[k + "_n"] = len(v)
            agg["n"] = len(rows)
            table[(name, m)] = agg
    return table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--json", default=os.path.join(LOCAL, "source_comparison.json"))
    args = ap.parse_args()
    app = QgsApplication([], False)
    app.initQgis()
    from fao56_cwr_mapper.qgis_processing.field_cwr_algorithm import FieldCropWaterRequirement as Alg
    Alg.fetcher = staticmethod(power_urllib.fetcher)
    os.makedirs(LOCAL, exist_ok=True)
    station_file, notes = station_csv_file([args.year - 1, args.year])
    stations, layer, tmp = station_layer(), fields_layer(args.year), tempfile.mkdtemp()
    results = {}
    for source in SOURCES:
        for pe in PE_METHODS:
            results["{}|{}".format(SOURCES[source], PE_METHODS[pe])] = run(
                Alg, layer, source, pe, station_file, stations, tmp)
    inputs = daily_inputs(args.year, station_file)
    months = [(args.year, m) for m in range(4, 11)]
    table = monthly(inputs, months)
    data = {"year": args.year, "gsod_notes": notes,
            "results": {k: {f: {kk: (str(vv.toPyDate()) if hasattr(vv, "toPyDate") else vv)
                                for kk, vv in row.items()} for f, row in v.items()}
                        for k, v in results.items()},
            "monthly": {"{}|{}-{:02d}".format(n, *m): v for (n, m), v in table.items()},
            "elevation": {n: s["elevation"] for n, s in inputs.items()}}
    with open(args.json, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, default=str)
    print("written", args.json)
    del Alg
    app.exitQgis()


if __name__ == "__main__":
    main()
