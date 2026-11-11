"""Headless QGIS test of the Processing algorithm (skipped without QGIS).

Run with the QGIS Python interpreter, e.g. on macOS:
    QGIS_PREFIX=/Applications/QGIS.app/Contents/MacOS \\
    PYTHONPATH=/Applications/QGIS.app/Contents/Resources/qgis/python/plugins \\
    /Applications/QGIS.app/Contents/MacOS/python -m unittest tests.test_qgis_algorithm -v

Climate data comes from a fake fetcher that returns constant weather for the
requested dates, so results are deterministic and no network is needed.
"""

import csv
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

try:
    from qgis.core import (QgsApplication, QgsFeature, QgsGeometry, QgsPointXY,
                           QgsProcessingContext, QgsProcessingFeedback, QgsVectorLayer, NULL)
    from qgis.PyQt.QtCore import QDate
    HAVE_QGIS = True
except ImportError:
    HAVE_QGIS = False

WEATHER = {"T2M_MAX": 30.0, "T2M_MIN": 18.0, "T2MDEW": 14.0, "RH2M": 55.0, "WS2M": 2.0,
           "ALLSKY_SFC_SW_DWN": 25.0, "PRECTOTCORR": 0.0}


OPEN_METEO = {"temperature_2m_max": 30.0, "temperature_2m_min": 18.0, "dew_point_2m_mean": 14.0,
              "relative_humidity_2m_mean": 55.0, "wind_speed_10m_mean": 2.67,
              "shortwave_radiation_sum": 25.0, "precipitation_sum": 0.0, "et0_fao_evapotranspiration": 5.0}
OPEN_METEO_UNITS = {"temperature_2m_max": "°C", "temperature_2m_min": "°C", "dew_point_2m_mean": "°C",
                    "relative_humidity_2m_mean": "%", "wind_speed_10m_mean": "m/s",
                    "shortwave_radiation_sum": "MJ/m²", "precipitation_sum": "mm",
                    "et0_fao_evapotranspiration": "mm"}


def fake_open_meteo(q, null_last=0):
    start = date.fromisoformat(q["start_date"][0])
    end = date.fromisoformat(q["end_date"][0])
    n = (end - start).days + 1
    daily = {v: [x] * (n - null_last) + [None] * null_last for v, x in OPEN_METEO.items()}
    daily["time"] = [(start + timedelta(days=k)).isoformat() for k in range(n)]
    return json.dumps({"latitude": float(q["latitude"][0]), "longitude": float(q["longitude"][0]),
                       "elevation": 100.0, "daily_units": OPEN_METEO_UNITS, "daily": daily}).encode()


def fake_fetcher(url):
    q = parse_qs(urlparse(url).query)
    if "open-meteo.com" in url:
        return fake_open_meteo(q)
    start = datetime.strptime(q["start"][0], "%Y%m%d").date()
    end = datetime.strptime(q["end"][0], "%Y%m%d").date()
    days = [(start + timedelta(days=k)).strftime("%Y%m%d") for k in range((end - start).days + 1)]
    body = {
        "geometry": {"coordinates": [float(q["longitude"][0]), float(q["latitude"][0]), 100.0]},
        "properties": {"parameter": {p: {d: v for d in days} for p, v in WEATHER.items()}},
        "header": {"fill_value": -999.0, "sources": ["FAKE"]},
        "parameters": {"ALLSKY_SFC_SW_DWN": {"units": "MJ/m^2/day"}},
    }
    return json.dumps(body).encode()


@unittest.skipUnless(HAVE_QGIS, "QGIS Python bindings not available")
class TestFieldAlgorithm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication([], False)
        cls.app.initQgis()
        from fao56_cwr_mapper.qgis_processing.field_cwr_algorithm import FieldCropWaterRequirement
        cls.Alg = FieldCropWaterRequirement
        cls.Alg.fetcher = staticmethod(fake_fetcher)

    def run_alg(self, layer, **params):
        alg = self.Alg()
        alg.initAlgorithm()
        tmp = tempfile.mkdtemp()
        base = {"INPUT": layer, "OUTPUT": "memory:", "USE_CACHE": False,
                "OUTPUT_DAILY": os.path.join(tmp, "daily.csv"),
                "OUTPUT_DEKAD": os.path.join(tmp, "dekad.csv")}
        base.update(params)
        context = QgsProcessingContext()
        context.setEllipsoid("EPSG:7030")
        res, ok = alg.run(base, context, QgsProcessingFeedback())
        self.assertTrue(ok, res)
        out = context.getMapLayer(res["OUTPUT"]) or context.takeResultLayer(res["OUTPUT"]) \
            or QgsVectorLayer(res["OUTPUT"], "result", "ogr")
        return {f["name"]: f for f in out.getFeatures()}, res

    def polygon_layer(self):
        # 100 m x 100 m squares near Tekirdag, UTM zone 35N
        layer = QgsVectorLayer("Polygon?crs=EPSG:32635&field=name:string&field=crop:string"
                               "&field=planted:date", "fields", "memory")
        rows = [("tomato_default", None, None),
                ("sunflower", "Sunflower - irrigated", QDate(2025, 4, 20)),
                ("typo", "Tomatoe", None),
                ("garlic", "Garlic", None),
                ("maize", "Maize, Field (grain) (field corn) - grain dried in field", QDate(2025, 4, 20))]
        feats = []
        for i, (name, crop, planted) in enumerate(rows):
            x, y = 542000 + i * 500, 4536000
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(x, y), QgsPointXY(x + 100, y),
                                                      QgsPointXY(x + 100, y + 100), QgsPointXY(x, y + 100)]]))
            f.setAttributes([name, crop if crop else NULL, planted if planted else NULL])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        return layer

    def test_polygons(self):
        feats, res = self.run_alg(self.polygon_layer(), CROP_FIELD="crop", PLANTING_FIELD="planted",
                                  PLANTING_DATE=QDate(2025, 5, 1))
        t = feats["tomato_default"]
        self.assertEqual(t["crop_used"], "Tomato")
        self.assertIn("Mediterranean", t["stage_used"])                 # region keyword
        self.assertEqual(t["season_beg"], QDate(2025, 5, 1))
        self.assertEqual(t["miss_days"], 0)
        self.assertEqual(t["status"], "ok")
        self.assertEqual(t["nir_period"], "dekad")
        self.assertAlmostEqual(t["area_m2"], 10000, delta=20)           # ellipsoidal, ~0.1 %
        self.assertAlmostEqual(t["NIR_mm"], t["ETc_mm"], delta=0.2)     # dry fake weather
        self.assertAlmostEqual(t["NIR_m3"], t["NIR_mm"] * t["area_m2"] / 1000, delta=1)
        self.assertAlmostEqual(t["NIR_m3_da"], t["NIR_mm"], delta=0.01)

        s = feats["sunflower"]
        self.assertEqual(s["crop_used"], "Sunflower - irrigated")
        self.assertEqual(s["season_beg"], QDate(2025, 4, 20))           # from the date field

        self.assertTrue(feats["typo"]["status"].startswith("error"))
        self.assertIn("Tomato", feats["typo"]["status"])                 # suggestion
        self.assertEqual(feats["typo"]["NIR_mm"], NULL)
        self.assertIn("no stage lengths", feats["garlic"]["status"])

        m = feats["maize"]                                             # no Mediterranean maize row
        self.assertTrue(m["status"].startswith("warning: no FAO-56 Table 11 example"))
        self.assertIn("planting month", m["status"])
        self.assertIn("April", m["stage_used"])
        self.assertGreater(m["NIR_mm"], 0)

        with open(res["OUTPUT_DAILY"], newline="") as fh:
            daily = list(csv.DictReader(fh))
        self.assertEqual(len(daily), 145 + 130 + 180)                    # tomato, sunflower, maize
        with open(res["OUTPUT_DEKAD"], newline="") as fh:
            dekads = [r for r in csv.DictReader(fh) if int(r["fid"]) == t.id()]
        self.assertAlmostEqual(sum(float(r["NIR"]) for r in dekads), t["NIR_mm"], delta=0.2)

    def test_stage_length_fields_and_points(self):
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=crop:string"
                               "&field=li:integer&field=ld:integer&field=lm:integer&field=ll:integer",
                               "pts", "memory")
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(27.51, 40.98)))
        f.setAttributes(["garlic_pt", "Garlic", 20, 30, 60, 20])
        layer.dataProvider().addFeatures([f])
        feats, _ = self.run_alg(layer, CROP_FIELD="crop", L_INI_FIELD="li", L_DEV_FIELD="ld",
                                L_MID_FIELD="lm", L_LATE_FIELD="ll", PLANTING_DATE=QDate(2025, 3, 1))
        g = feats["garlic_pt"]
        self.assertEqual(g["status"], "ok")
        self.assertIn("130 days", g["stage_used"])
        self.assertEqual(g["season_end"], QDate(2025, 3, 1).addDays(129))
        self.assertEqual(g["area_m2"], NULL)                            # points have no area
        self.assertEqual(g["NIR_m3"], NULL)
        self.assertGreater(g["NIR_m3_ha"], 0)

    def test_region_field_on_sample_data(self):
        sample = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "sample_data", "tekirdag_fields.gpkg")
        layer = QgsVectorLayer(sample + "|layername=fields", "sample", "ogr")
        self.assertTrue(layer.isValid())
        feats, _ = self.run_alg(layer, CROP_FIELD="crop", PLANTING_FIELD="planted",
                                REGION_FIELD="region")
        maize = feats["Field A"]
        self.assertEqual(maize["status"], "ok")                       # 'Spain' from the field
        self.assertIn("Spain", maize["stage_used"])
        self.assertEqual(maize["season_end"], QDate(2025, 4, 20).addDays(149))   # 150 days
        for name in ("Field B", "Field C", "Field D"):
            with self.subTest(field=name):
                self.assertEqual(feats[name]["status"], "ok")
                self.assertRegex(feats[name]["stage_used"], "Medit")

        # with the field switched off, the keyword applies to all and maize falls back to the month rule
        feats, _ = self.run_alg(layer, CROP_FIELD="crop", PLANTING_FIELD="planted", REGION_FIELD="")
        self.assertTrue(feats["Field A"]["status"].startswith("warning"))

    def sample_layer(self):
        sample = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "sample_data", "tekirdag_fields.gpkg")
        return QgsVectorLayer(sample + "|layername=fields", "sample", "ogr")

    def test_default_field_names(self):
        # 'crop', 'planted' and 'region' are picked up without naming them
        feats, _ = self.run_alg(self.sample_layer())
        self.assertIn("Spain", feats["Field A"]["stage_used"])
        self.assertEqual(feats["Field A"]["season_beg"], QDate(2025, 4, 20))
        self.assertTrue(all(f["status"] == "ok" for f in feats.values()))

    def test_one_download_per_grid_cell(self):
        calls = []

        def counting_fetcher(url):
            calls.append(url)
            return fake_fetcher(url)

        self.Alg.fetcher = staticmethod(counting_fetcher)
        try:
            # polygon_layer: five fields within 2 km -> one cell; 'typo' and 'garlic' fail before download
            feats, _ = self.run_alg(self.polygon_layer(), PLANTING_DATE=QDate(2025, 5, 1))
            self.assertEqual(len(calls), 1)
            self.assertEqual(sum(f["status"] == "ok" for f in feats.values()), 2)
            # one more point in another cell (Edirne, 41.68 N 26.56 E) -> two downloads
            layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", "pts", "memory")
            pts = []
            for name, x, y in (("a", 27.51, 40.98), ("b", 27.60, 40.90), ("c", 26.56, 41.68)):
                f = QgsFeature(layer.fields())
                f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                f.setAttributes([name])
                pts.append(f)
            layer.dataProvider().addFeatures(pts)
            del calls[:]
            feats, _ = self.run_alg(layer, PLANTING_DATE=QDate(2025, 5, 1))
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(f["status"] == "ok" for f in feats.values()))
        finally:
            self.Alg.fetcher = staticmethod(fake_fetcher)

    def test_report_output(self):
        tmp = tempfile.mkdtemp()
        for name in ("report.html", "report.txt"):
            path = os.path.join(tmp, name)
            _, res = self.run_alg(self.polygon_layer(), OUTPUT_REPORT=path,
                                  PLANTING_DATE=QDate(2025, 5, 1))
            self.assertEqual(res["OUTPUT_REPORT"], path)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            with self.subTest(report=name):
                self.assertIn("tomato_default", text)                 # labels from the 'name' field
                self.assertIn("Tomatoe", text)                        # failing feature listed
                self.assertIn("field 'crop'", text)
                self.assertIn("EPSG:32635", text)
                self.assertIn("No soil water storage", text)

    def test_wrong_planting_field_stops_early(self):
        alg = self.Alg()
        alg.initAlgorithm()
        feedback = QgsProcessingFeedback()
        res, ok = alg.run({"INPUT": self.sample_layer(), "OUTPUT": "memory:", "USE_CACHE": False,
                           "PLANTING_FIELD": "region"}, QgsProcessingContext(), feedback)
        self.assertFalse(ok)

    def test_result_style(self):
        from qgis.core import QgsProcessingOutputLayerDefinition, QgsProject
        alg = self.Alg()
        alg.initAlgorithm()
        context = QgsProcessingContext()
        context.setProject(QgsProject.instance())
        out_def = QgsProcessingOutputLayerDefinition("TEMPORARY_OUTPUT", QgsProject.instance())
        params = {"INPUT": self.polygon_layer(), "OUTPUT": out_def, "USE_CACHE": False,
                  "CROP_FIELD": "crop", "PLANTING_FIELD": "planted",
                  "PLANTING_DATE": QDate(2025, 5, 1)}
        res, ok = alg.run(params, context, QgsProcessingFeedback())
        self.assertTrue(ok)
        details = context.layerToLoadOnCompletionDetails(res["OUTPUT"])
        self.assertIsNotNone(details.postProcessor())
        layer = context.getMapLayer(res["OUTPUT"])
        details.postProcessor().postProcessLayer(layer, context, QgsProcessingFeedback())

        r = layer.renderer()
        self.assertEqual(r.type(), "graduatedSymbol")
        labels = [rg.label() for rg in r.ranges()]
        self.assertEqual(labels[-1], "no value (see status)")          # typo/garlic rows stay visible
        self.assertTrue(all(l.endswith(" mm") for l in labels[:-1]))
        values = [f["NIR_mm"] for f in layer.getFeatures() if f["NIR_mm"] != NULL]
        self.assertLessEqual(r.ranges()[0].lowerValue(), min(values))
        self.assertGreaterEqual(r.ranges()[-2].upperValue(), max(values))
        colors = [rg.symbol().color().name() for rg in r.ranges()[:-1]]
        self.assertEqual(colors[0], "#eff3ff")                        # light = low requirement

    def test_style_saved_in_geopackage(self):
        from fao56_cwr_mapper.qgis_processing.styling import apply_nir_style
        path = os.path.join(tempfile.mkdtemp(), "result.gpkg")
        _, res = self.run_alg(self.polygon_layer(), OUTPUT=path, CROP_FIELD="crop",
                              PLANTING_FIELD="planted", PLANTING_DATE=QDate(2025, 5, 1))
        layer = QgsVectorLayer(res["OUTPUT"], "result", "ogr")
        self.assertTrue(apply_nir_style(layer))
        reopened = QgsVectorLayer(res["OUTPUT"], "again", "ogr")     # loads the default style
        self.assertEqual(reopened.renderer().type(), "graduatedSymbol")

    # --- weather stations -------------------------------------------------

    def station_csv(self, rows_for):
        """CSV path with daily rows for 2024-10-01 .. 2025-12-31; rows_for(day) -> {station: row}."""
        from datetime import timedelta
        path = os.path.join(tempfile.mkdtemp(), "stations.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("station,date,tmax,tmin,tdew,u2,rs,precip\n")
            d = date(2024, 10, 1)
            while d <= date(2025, 12, 31):
                for sid, row in rows_for(d).items():
                    fh.write("{},{},{}\n".format(sid, d.isoformat(), row))
                d += timedelta(days=1)
        return path

    def station_layer(self, stations, id_type="string"):
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=station:{}&field=elevation:double".format(id_type),
                               "stations", "memory")
        feats = []
        for sid, lon, lat, elev in stations:
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
            f.setAttributes([sid, elev])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        return layer

    def no_download(self):
        def refuse(url):
            raise AssertionError("station mode must not download")
        self.Alg.fetcher = staticmethod(refuse)
        self.addCleanup(setattr, self.Alg, "fetcher", staticmethod(fake_fetcher))

    def test_nearest_station(self):
        self.no_download()
        csv_path = self.station_csv(lambda d: {"A": "30,18,14,2,25,0", "B": "28,16,,,,0"})
        stations = self.station_layer([("A", 27.50, 40.97, 4.0), ("B", 26.56, 41.68, 51.0)])
        feats, res = self.run_alg(self.sample_layer(), CLIMATE_SOURCE=1, STATION_CSV=csv_path,
                                  STATION_LAYER=stations, STATION_ID_FIELD="station",
                                  STATION_ELEV_FIELD="elevation", MAX_DISTANCE_KM=50,
                                  OUTPUT_REPORT=os.path.join(tempfile.mkdtemp(), "r.txt"))
        for name, f in feats.items():
            with self.subTest(field=name):
                self.assertEqual(f["clim_src"], "Weather station A")
                self.assertLess(f["station_km"], 10)
                self.assertEqual(f["elev_m"], 4.0)
                self.assertEqual(f["status"], "ok")             # A has all inputs: nothing estimated
                self.assertEqual(f["miss_days"], 0)
        with open(res["OUTPUT_REPORT"], encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("Weather station data (CSV)", text)
        self.assertIn("stations.csv", text)
        self.assertNotIn("NASA POWER daily point API", text)

    def test_station_estimates_and_distance_limit(self):
        self.no_download()
        csv_path = self.station_csv(lambda d: {"B": "28,16,,,,0"})
        stations = self.station_layer([("B", 27.55, 40.99, 10.0)])
        feats, _ = self.run_alg(self.sample_layer(), CLIMATE_SOURCE=1, STATION_CSV=csv_path,
                                STATION_LAYER=stations, MAX_DISTANCE_KM=50, KRS=1)
        f = feats["Field A"]
        self.assertTrue(f["status"].startswith("warning"))
        for word in ("Eq. 48", "Eq. 50", "u2 = 2 m/s"):
            self.assertIn(word, f["status"])
        far = self.station_layer([("B", 26.56, 41.68, 10.0)])           # Edirne, ~95 km away
        feats, _ = self.run_alg(self.sample_layer(), CLIMATE_SOURCE=1, STATION_CSV=csv_path,
                                STATION_LAYER=far, MAX_DISTANCE_KM=50)
        self.assertIn("no weather station within 50 km", feats["Field A"]["status"])

    def test_station_input_errors(self):
        csv_path = self.station_csv(lambda d: {"A": "30,18,14,2,25,0"})
        no_elev = QgsVectorLayer("Point?crs=EPSG:4326&field=station:string", "s", "memory")
        f = QgsFeature(no_elev.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(27.5, 40.97)))
        f.setAttributes(["A"])
        no_elev.dataProvider().addFeatures([f])
        alg = self.Alg()
        alg.initAlgorithm()
        for params in ({"STATION_LAYER": no_elev, "STATION_CSV": csv_path},       # no elevation field
                       {"STATION_CSV": csv_path}):                                 # no station layer
            with self.subTest(params=sorted(params)):
                res, ok = alg.run(dict({"INPUT": self.sample_layer(), "OUTPUT": "memory:",
                                        "CLIMATE_SOURCE": 1}, **params),
                                  QgsProcessingContext(), QgsProcessingFeedback())
                self.assertFalse(ok)

    def test_single_station_and_numeric_id(self):
        self.no_download()
        path = os.path.join(tempfile.mkdtemp(), "one.csv")
        with open(path, "w", encoding="utf-8") as fh:            # MGM style, no station column
            fh.write("Tarih;Maksimum Sıcaklık (°C);Minimum Sıcaklık (°C);Ortalama Nem (%);"
                     "Rüzgar Hızı (m/s);Güneşlenme Süresi (saat);Yağış (mm)\n")
            from datetime import timedelta
            d = date(2024, 10, 1)
            while d <= date(2025, 12, 31):
                fh.write("{:%d.%m.%Y};30,5;18,2;60;3,0;11,5;0\n".format(d))
                d += timedelta(days=1)
        stations = self.station_layer([(17056, 27.50, 40.97, 4.0)], id_type="integer")
        feats, _ = self.run_alg(self.sample_layer(), CLIMATE_SOURCE=1, STATION_CSV=path,
                                STATION_LAYER=stations, WIND_HEIGHT=10)
        f = feats["Field C"]
        self.assertEqual((f["clim_src"], f["status"]), ("Weather station 17056", "ok"))
        self.assertGreater(f["NIR_mm"], 0)

    def thiessen_case(self, rows_for, stations, max_km=50):
        """Square field (2 km) centred on 40.98 N 27.50 E, between the given stations."""
        self.no_download()
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=crop:string"
                               "&field=planted:date", "f", "memory")
        f = QgsFeature(layer.fields())
        d = 0.012
        f.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(27.50 - d, 40.98 - d), QgsPointXY(27.50 + d, 40.98 - d),
                                                  QgsPointXY(27.50 + d, 40.98 + d), QgsPointXY(27.50 - d, 40.98 + d)]]))
        f.setAttributes(["mid", "Tomato", QDate(2025, 5, 1)])
        layer.dataProvider().addFeatures([f])
        feats, _ = self.run_alg(layer, CLIMATE_SOURCE=1, STATION_CSV=self.station_csv(rows_for),
                                STATION_LAYER=self.station_layer(stations), ASSIGNMENT=1,
                                MAX_DISTANCE_KM=max_km)
        return feats["mid"]

    def test_thiessen_half_and_half(self):
        west_east = [("W", 27.40, 40.98, 10.0), ("E", 27.60, 40.98, 10.0)]
        hot_cool = lambda d: {"W": "34,20,14,2,27,0", "E": "26,16,14,2,23,0"}
        mid = self.thiessen_case(hot_cool, west_east)
        weights = dict(p.split(":") for p in mid["stn_weight"].split())
        self.assertEqual(set(weights), {"W", "E"})
        self.assertAlmostEqual(float(weights["W"]), 0.5, delta=0.01)    # bisector through the field
        self.assertTrue(mid["clim_src"].startswith("Thiessen-weighted stations"))
        only_w = self.thiessen_case(hot_cool, west_east[:1])
        only_e = self.thiessen_case(hot_cool, west_east[1:])
        self.assertLess(only_e["ETo_mm"], mid["ETo_mm"])
        self.assertLess(mid["ETo_mm"], only_w["ETo_mm"])
        self.assertAlmostEqual(mid["ETo_mm"], (only_w["ETo_mm"] + only_e["ETo_mm"]) / 2, delta=1.5)
        self.assertEqual(only_w["stn_weight"], "W:1.000")

    def test_thiessen_distance_limit_and_reweighting(self):
        # E is 60 km away: left out with a 50 km limit, so W alone remains
        far = self.thiessen_case(lambda d: {"W": "30,18,14,2,25,0", "E": "26,16,14,2,23,0"},
                                 [("W", 27.49, 40.98, 10.0), ("E", 28.21, 40.98, 10.0)], max_km=50)
        self.assertEqual(far["stn_weight"], "W:1.000")
        # E has no data in July: its weight goes to W on those days, with a warning
        gaps = self.thiessen_case(lambda d: {"W": "30,18,14,2,25,0",
                                             "E": "-,-,-,-,-,-" if d.month == 7 else "30,18,14,2,25,0"},
                                  [("W", 27.40, 40.98, 10.0), ("E", 27.60, 40.98, 10.0)])
        self.assertIn("Station weights rescaled on 31 season day(s)", gaps["status"])
        self.assertEqual(gaps["miss_days"], 0)

    def test_open_meteo(self):
        calls = []

        def counting(url):
            calls.append(url)
            return fake_fetcher(url)

        self.Alg.fetcher = staticmethod(counting)
        self.addCleanup(setattr, self.Alg, "fetcher", staticmethod(fake_fetcher))
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "report.html")
        feats, _ = self.run_alg(self.polygon_layer(), CLIMATE_SOURCE=2, PLANTING_DATE=QDate(2025, 5, 1),
                                OUTPUT_REPORT=path)
        # three valid fields 500 m apart: one request point per 0.01 degree
        points = {(parse_qs(urlparse(u).query)["latitude"][0], parse_qs(urlparse(u).query)["longitude"][0])
                  for u in calls}
        self.assertEqual(len(calls), len(points))
        self.assertTrue(all("models=era5_seamless" in u and "wind_speed_unit=ms" in u for u in calls))
        ok = [f for f in feats.values() if f["status"] == "ok"]
        self.assertEqual(len(ok), 2)
        self.assertTrue(all(f["clim_src"].startswith("Open-Meteo ERA5-Seamless") for f in ok))
        self.assertTrue(all(f["elev_m"] == 100.0 for f in ok))
        # same weather as the NASA POWER fake (2.67 m/s at 10 m is 2.0 m/s at 2 m): same ETo
        power, _ = self.run_alg(self.polygon_layer(), PLANTING_DATE=QDate(2025, 5, 1))
        for name in ("tomato_default", "sunflower"):
            self.assertAlmostEqual(feats[name]["ETo_mm"], power[name]["ETo_mm"], delta=0.5)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for part in ("Open-Meteo Historical Weather API", "non-commercial", "Weather data by Open-Meteo.com",
                     "Zippenfenig", "ERA5-Seamless"):
            self.assertIn(part, text)
        self.assertNotIn("NASA POWER Project", text)

        del calls[:]
        self.run_alg(self.polygon_layer(), CLIMATE_SOURCE=2, OPEN_METEO_MODEL=2,
                     PLANTING_DATE=QDate(2025, 5, 1))
        self.assertTrue(calls and all("models=best_match" in u for u in calls))

    def test_open_meteo_delay_counts_missing_days(self):
        def delayed(url):
            return fake_open_meteo(parse_qs(urlparse(url).query), null_last=5)

        self.Alg.fetcher = staticmethod(delayed)
        self.addCleanup(setattr, self.Alg, "fetcher", staticmethod(fake_fetcher))
        feats, _ = self.run_alg(self.polygon_layer(), CLIMATE_SOURCE=2, PLANTING_DATE=QDate(2025, 5, 1))
        self.assertEqual(feats["tomato_default"]["miss_days"], 5)
        self.assertTrue(feats["tomato_default"]["status"].startswith("warning"))

    def test_provider_registration(self):
        from fao56_cwr_mapper.qgis_processing.provider import FAO56Provider
        provider = FAO56Provider()
        self.assertTrue(QgsApplication.processingRegistry().addProvider(provider))
        alg = QgsApplication.processingRegistry().algorithmById("fao56cwr:fieldcropwaterrequirement")
        self.assertIsNotNone(alg)
        QgsApplication.processingRegistry().removeProvider(provider)


if __name__ == "__main__":
    unittest.main()
