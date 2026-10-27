"""Tests for the NASA POWER client and the daily ETo series (offline).

tests/data/power_tekirdag_20250701_05.json is a real API response
(Tekirdag, 40.98 N 27.51 E, 1-5 July 2025, community=AG).
"""

import copy
import json
import os
import shutil
import tempfile
import unittest
from datetime import date

from fao56_cwr_mapper.climate_sources import nasa_power as np_
from fao56_cwr_mapper.core import eto_series, fao56

DATA = os.path.join(os.path.dirname(__file__), "data", "power_tekirdag_20250701_05.json")


def load_fixture():
    with open(DATA, encoding="utf-8") as fh:
        return json.load(fh)


class TestBuildUrl(unittest.TestCase):
    def test_url(self):
        url = np_.build_url(40.98, 27.51, date(2025, 7, 1), date(2025, 7, 5))
        self.assertTrue(url.startswith(np_.BASE_URL + "?"))
        for part in ("community=AG", "latitude=40.9800", "longitude=27.5100",
                     "start=20250701", "end=20250705", "format=JSON",
                     "parameters=T2M_MAX,T2M_MIN,T2MDEW,RH2M,WS2M,ALLSKY_SFC_SW_DWN,PRECTOTCORR"):
            self.assertIn(part, url)

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            np_.build_url(95, 0, date(2025, 1, 1), date(2025, 1, 2))
        with self.assertRaises(ValueError):
            np_.build_url(0, 0, date(2025, 1, 2), date(2025, 1, 1))


class TestCellKey(unittest.TestCase):
    # Edges measured against the live API (v2.10.1, Oct 2026)

    def test_same_cell(self):
        # these pairs returned identical data for 365 days and all 7 parameters
        for a, b in (((40.76, 27.19), (40.99, 27.80)), ((41.01, 27.20), (41.24, 27.81)),
                     ((-33.9, 18.4), (-33.76, 18.2))):
            with self.subTest(a=a, b=b):
                self.assertEqual(np_.cell_key(*a), np_.cell_key(*b))

    def test_measured_edges(self):
        # meteorology edges at 40.75 / 41.25 N and 27.1875 / 27.8125 E, radiation at 41 N, 27 / 28 E
        pairs = [((40.70, 27.51), (40.75, 27.51)), ((41.20, 27.51), (41.25, 27.51)),
                 ((40.98, 27.15), (40.98, 27.20)), ((40.98, 27.80), (40.98, 27.85)),
                 ((40.95, 27.51), (41.00, 27.51)), ((40.98, 26.95), (40.98, 27.00)),
                 ((40.98, 27.51), (41.02, 27.51))]
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                self.assertNotEqual(np_.cell_key(*a), np_.cell_key(*b))

    def test_point_on_edge_belongs_to_upper_cell(self):
        for edge, below, above in (((40.75, 27.51), (40.74, 27.51), (40.76, 27.51)),
                                   ((41.00, 27.51), (40.99, 27.51), (41.01, 27.51)),
                                   ((40.98, 27.1875), (40.98, 27.18), (40.98, 27.195)),
                                   ((-40.75, 147.0), (-40.76, 147.0), (-40.74, 147.0)),
                                   ((-9.7, -60.0), (-9.7, -60.01), (-9.7, -59.99))):
            with self.subTest(edge=edge):
                self.assertEqual(np_.cell_key(*edge), np_.cell_key(*above))
                self.assertNotEqual(np_.cell_key(*edge), np_.cell_key(*below))


class TestParse(unittest.TestCase):
    def test_real_response(self):
        s = np_.parse_response(load_fixture())
        self.assertEqual((s.latitude, s.longitude, s.elevation), (40.98, 27.51, 98.23))
        self.assertEqual(s.api_version, "v2.10.1")
        self.assertEqual(s.sources, ["MERRA2", "SYN1DEG", "POWER"])
        self.assertEqual(len(s.days), 5)
        d = s.days[0]
        self.assertEqual(d.day, date(2025, 7, 1))
        self.assertEqual((d.tmax, d.tmin, d.tdew, d.rh, d.u2, d.rs, d.precip),
                         (32.29, 20.73, 16.45, 55.43, 2.71, 22.16, 0.0))
        self.assertEqual(s.missing_days(), [])

    def test_fill_values_become_none(self):
        data = load_fixture()
        data["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]["20250705"] = -999.0
        s = np_.parse_response(data)
        self.assertIsNone(s.days[-1].rs)
        self.assertEqual(s.missing_days(), [date(2025, 7, 5)])

    def test_kwh_radiation_converted(self):
        # community=RE returns kW-hr/m^2/day; live value for 1 July 2025 was 6.1543
        data = load_fixture()
        data["parameters"]["ALLSKY_SFC_SW_DWN"]["units"] = "kW-hr/m^2/day"
        data["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]["20250701"] = 6.1543
        self.assertAlmostEqual(np_.parse_response(data).days[0].rs, 22.16, delta=0.01)

    def test_api_error_body(self):
        body = {"detail": [{"msg": "Input should be less than or equal to 90"}]}
        with self.assertRaisesRegex(np_.PowerError, "less than or equal to 90"):
            np_.parse_response(body)

    def test_missing_parameter(self):
        data = load_fixture()
        del data["properties"]["parameter"]["WS2M"]
        with self.assertRaisesRegex(np_.PowerError, "WS2M"):
            np_.parse_response(data)


class TestFetchAndCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.calls = []
        with open(DATA, "rb") as fh:
            self.raw = fh.read()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def fetcher(self, url):
        self.calls.append(url)
        return self.raw

    def test_cache_hit_skips_network(self):
        args = (40.98, 27.51, date(2025, 7, 1), date(2025, 7, 5))
        np_.fetch(*args, fetcher=self.fetcher, cache_dir=self.tmp)
        s = np_.fetch(*args, fetcher=self.fetcher, cache_dir=self.tmp)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(s.days), 5)

    def test_incomplete_response_not_cached(self):
        data = load_fixture()
        data["properties"]["parameter"]["T2M_MAX"]["20250705"] = -999.0
        self.raw = json.dumps(data).encode()
        args = (40.98, 27.51, date(2025, 7, 1), date(2025, 7, 5))
        np_.fetch(*args, fetcher=self.fetcher, cache_dir=self.tmp)
        np_.fetch(*args, fetcher=self.fetcher, cache_dir=self.tmp)
        self.assertEqual(len(self.calls), 2)

    def test_future_start_rejected(self):
        with self.assertRaises(ValueError):
            np_.fetch(0, 0, date(2026, 11, 1), date(2026, 11, 5),
                      fetcher=self.fetcher, today=date(2026, 10, 25))
        self.assertEqual(self.calls, [])


class TestEtoSeries(unittest.TestCase):
    def setUp(self):
        self.series = np_.parse_response(load_fixture())

    def test_first_day_matches_direct_calculation(self):
        rows = eto_series.daily_eto_series(self.series.days, 40.98, 98.23)
        d = self.series.days[0]
        expected = fao56.daily_eto(d.day, 40.98, 98.23, d.tmax, d.tmin, d.u2,
                                   fao56.actual_vapour_pressure_from_tdew(d.tdew), d.rs)["ETo"]
        self.assertAlmostEqual(rows[0]["ETo"], expected, places=12)
        self.assertEqual(rows[0]["ea_method"], eto_series.EA_TDEW)
        # Plausibility for a hot, dry Thracian July: 4-9 mm/day
        for r in rows:
            self.assertTrue(4.0 < r["ETo"] < 9.0, r["ETo"])

    def test_rh_fallback_and_missing(self):
        days = copy.deepcopy(self.series.days)
        days[1].tdew = None          # -> Eq. 19 from RH2M
        days[2].rs = None            # -> missing
        rows = eto_series.daily_eto_series(days, 40.98, 98.23)
        self.assertEqual(rows[1]["ea_method"], eto_series.EA_RHMEAN)
        self.assertIsNotNone(rows[1]["ETo"])
        self.assertTrue(rows[2]["missing"])
        self.assertIsNone(rows[2]["ETo"])


if __name__ == "__main__":
    unittest.main()
