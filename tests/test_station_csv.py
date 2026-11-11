"""Tests for the weather station CSV reader."""

import os
import tempfile
import unittest
from datetime import date

from fao56_cwr_mapper.climate_sources import station_csv as sc
from fao56_cwr_mapper.core import eto_series as es
from fao56_cwr_mapper.core import fao56

ENGLISH = """station,date,tmax,tmin,tdew,u2,rs,precip
A,2025-07-01,32.3,20.7,16.5,2.7,22.2,0
A,2025-07-02,30.4,18.8,13.2,3.7,29.7,1.5
B,2025-07-01,29.0,17.0,,,,0
"""

# MGM-style export: Turkish headers with units, ';' and decimal comma, DD.MM.YYYY, wind at 10 m
TURKISH = """İstasyon No;Tarih;Maksimum Sıcaklık (°C);Minimum Sıcaklık (°C);Ortalama Nem (%);Rüzgar Hızı (m/s);Güneşlenme Süresi (saat);Yağış (mm)
17056;01.07.2025;31,2;19,4;61;3,5;12,1;0
17056;02.07.2025;29,8;18,9;-;-999;;2,4
"""


class TestColumns(unittest.TestCase):
    def test_normalise(self):
        self.assertEqual(sc.normalise("Tmax (°C)"), "tmax")
        self.assertEqual(sc.normalise("Güneşlenme Süresi [saat]"), "guneslenmesuresi")
        self.assertEqual(sc.normalise("İstasyon No"), "istasyonno")

    def test_turkish_header(self):
        cols = sc.match_columns(TURKISH.splitlines()[0].split(";"))
        self.assertEqual(set(cols), {"station", "date", "tmax", "tmin", "rh", "wind", "sunshine", "precip"})


class TestReading(unittest.TestCase):
    def test_english_two_stations(self):
        data = sc.read_station_csv(ENGLISH)
        self.assertEqual(sorted(data), ["A", "B"])
        a = data["A"].days
        self.assertEqual(len(a), 2)
        self.assertEqual((a[0].day, a[0].tmax, a[0].tdew, a[0].u2, a[0].rs, a[0].precip),
                         (date(2025, 7, 1), 32.3, 16.5, 2.7, 22.2, 0.0))
        b = data["B"].days[0]
        self.assertEqual((b.tdew, b.u2, b.rs), (None, None, None))
        self.assertEqual(data["A"].columns, ["precip", "rs", "tdew", "tmax", "tmin", "u2"])

    def test_turkish_mgm_style(self):
        rec = sc.read_station_csv(TURKISH, wind_height=10)["17056"].days
        self.assertEqual(rec[0].day, date(2025, 7, 1))
        self.assertEqual((rec[0].tmax, rec[0].tmin, rec[0].rh, rec[0].sunshine), (31.2, 19.4, 61.0, 12.1))
        self.assertAlmostEqual(rec[0].u2, fao56.wind_speed_2m(3.5, 10))       # Eq. 47: 10 m -> 2 m
        self.assertEqual((rec[1].rh, rec[1].u2, rec[1].sunshine, rec[1].precip), (None, None, None, 2.4))

    def test_single_station_without_id(self):
        data = sc.read_station_csv("date,tmax,tmin,precip\n2025-07-01,30,18,0\n")
        self.assertEqual(list(data), [sc.SINGLE_STATION])

    def test_data_problems_are_reported(self):
        text = ("station,date,tmax,tmin,rh,precip\n"
                "S,2025-07-01,15,25,120,0\n"
                "S,2025-07-01,30,18,50,-3\n")
        st = sc.read_station_csv(text)["S"]
        self.assertEqual(len(st.days), 1)                 # duplicate date: last row kept
        self.assertEqual((st.days[0].tmax, st.days[0].precip), (30.0, None))
        notes = " | ".join(st.warnings)
        for word in ("swapped", "outside 0-100", "negative precip", "duplicate"):
            self.assertIn(word, notes)

    def test_errors(self):
        with self.assertRaisesRegex(sc.StationDataError, "required column.*precip"):
            sc.read_station_csv("date,tmax,tmin\n2025-07-01,30,18\n")
        with self.assertRaisesRegex(sc.StationDataError, "Line 3: 'abc' is not a number"):
            sc.read_station_csv("date,tmax,tmin,precip\n2025-07-01,30,18,0\n2025-07-02,abc,18,0\n")
        with self.assertRaisesRegex(sc.StationDataError, "not a date"):
            sc.read_station_csv("date,tmax,tmin,precip\n07/2025,30,18,0\n")

    def test_windows_1254_file(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "wb") as fh:
            fh.write(TURKISH.encode("cp1254"))
        self.addCleanup(os.remove, path)
        self.assertEqual(sc.read_station_file(path)["17056"].days[0].tmax, 31.2)


class TestStationToEto(unittest.TestCase):
    def test_missing_inputs_are_estimated_and_listed(self):
        rec = sc.read_station_csv(ENGLISH)["B"].days
        rows = es.daily_eto_series(rec, 40.98, 4, estimation=es.Estimation(krs=0.19))
        self.assertFalse(rows[0]["missing"])
        self.assertEqual(rows[0]["estimated"], [es.EST_EA, es.EST_RS, es.EST_U2])

    def test_sunshine_from_turkish_file(self):
        rec = sc.read_station_csv(TURKISH, wind_height=10)["17056"].days
        rows = es.daily_eto_series(rec, 40.98, 4, estimation=es.Estimation())
        self.assertEqual(rows[0]["rs_method"], es.RS_SUNSHINE)
        self.assertEqual(rows[0]["ea_method"], es.EA_RHMEAN)
        self.assertEqual(rows[0]["estimated"], [])
        self.assertEqual(rows[1]["estimated"], [es.EST_EA, es.EST_RS, es.EST_U2])


class TestStationChainAndReport(unittest.TestCase):
    def test_run_field_with_station_series(self):
        from fao56_cwr_mapper import pipeline
        from fao56_cwr_mapper.core.crop_table import CropKc
        from fao56_cwr_mapper.core.stage_table import StageLengths

        def no_network(url):
            raise AssertionError("station data must not trigger a download")
        rec = sc.read_station_csv(ENGLISH)["B"].days
        series = sc.StationSeries("B", 40.98, 27.51, 4.0, rec)
        crop = CropKc("t", "Test", "", 0.5, 1.0, 0.5)
        stage = StageLengths("Test", "", 1, 1, 0, 0, 0, 1)
        s = pipeline.run_field(40.98, 27.51, crop, stage, date(2025, 7, 1), fetcher=no_network,
                               today=date(2026, 11, 11), series=series,
                               estimation=es.Estimation(krs=0.19))["summary"]
        self.assertEqual((s["climate_source"], s["elevation_m"], s["attribution"]),
                         ("Weather station B", 4.0, None))
        self.assertEqual(s["missing_days"], 0)
        self.assertEqual(s["estimated_days"], {es.EST_EA: 1, es.EST_RS: 1, es.EST_U2: 1})
        self.assertTrue(any("Eq. 50" in w for w in s["warnings"]))

    def test_report_for_station_source(self):
        from fao56_cwr_mapper.core import report
        settings = {"pe_fraction": 0.8, "nir_period": "dekad", "efficiency": None,
                    "climate": {"source": "station", "file": "stations.csv", "max_distance_km": 50,
                                "wind_height": 10, "estimation": True, "krs": 0.19}}
        rows = [{"feature": "F1", "status": "ok", "climate_sources": ["station 17056"],
                 "season_start": date(2025, 5, 1), "season_end": date(2025, 9, 1)}]
        text = report.build_text({"run_time": "x"}, settings, rows)
        for part in ("Weather station data (CSV)", "17056", "within 50 km",
                     "from 10 m to 2 m (Eq. 47)", "kRs = 0.19", "Eq. 48", "nearest station"):
            with self.subTest(part=part):
                self.assertIn(part, text)
        self.assertNotIn("NASA POWER", text)
        power = report.build_text({"run_time": "x"}, dict(settings, climate=None), rows)
        self.assertIn("NASA POWER daily point API", power)


if __name__ == "__main__":
    unittest.main()
