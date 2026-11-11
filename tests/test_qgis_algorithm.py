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


def fake_fetcher(url):
    q = parse_qs(urlparse(url).query)
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

    def test_provider_registration(self):
        from fao56_cwr_mapper.qgis_processing.provider import FAO56Provider
        provider = FAO56Provider()
        self.assertTrue(QgsApplication.processingRegistry().addProvider(provider))
        alg = QgsApplication.processingRegistry().algorithmById("fao56cwr:fieldcropwaterrequirement")
        self.assertIsNotNone(alg)
        QgsApplication.processingRegistry().removeProvider(provider)


if __name__ == "__main__":
    unittest.main()
