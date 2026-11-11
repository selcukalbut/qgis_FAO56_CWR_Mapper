"""Tests for the Open-Meteo client (offline, recorded response).

tests/data/openmeteo_tekirdag_20250701_05.json is a real response
(40.98 N 27.51 E, 1-5 July 2025, model era5_seamless).
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import date

from fao56_cwr_mapper.climate_sources import open_meteo as om
from fao56_cwr_mapper.core import eto_series, fao56

DATA = os.path.join(os.path.dirname(__file__), "data", "openmeteo_tekirdag_20250701_05.json")


def load():
    with open(DATA, encoding="utf-8") as fh:
        return json.load(fh)


class TestUrl(unittest.TestCase):
    def test_url(self):
        url = om.build_url(40.9812, 27.5149, date(2025, 7, 1), date(2025, 7, 5))
        self.assertTrue(url.startswith(om.BASE_URL + "?"))
        for part in ("latitude=40.98", "longitude=27.51", "start_date=2025-07-01", "end_date=2025-07-05",
                     "wind_speed_unit=ms", "timezone=auto", "models=era5_seamless",
                     "daily=temperature_2m_max,temperature_2m_min,dew_point_2m_mean"):
            self.assertIn(part, url)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            om.build_url(0, 0, date(2025, 1, 1), date(2025, 1, 2), model="era5_land")
        with self.assertRaises(ValueError):
            om.build_url(95, 0, date(2025, 1, 1), date(2025, 1, 2))


class TestParse(unittest.TestCase):
    def test_real_response(self):
        s = om.parse_response(load())
        self.assertEqual((s.latitude, s.longitude, s.elevation), (41.0, 27.5, 80.0))
        d = s.days[0]
        raw = load()["daily"]
        self.assertEqual((d.day, d.tmax, d.tmin, d.tdew, d.rh, d.rs, d.precip),
                         (date(2025, 7, 1), raw["temperature_2m_max"][0], raw["temperature_2m_min"][0],
                          raw["dew_point_2m_mean"][0], raw["relative_humidity_2m_mean"][0],
                          raw["shortwave_radiation_sum"][0], raw["precipitation_sum"][0]))
        self.assertAlmostEqual(d.u2, fao56.wind_speed_2m(raw["wind_speed_10m_mean"][0], 10))   # Eq. 47
        self.assertEqual(s.reference_eto[date(2025, 7, 1)], raw["et0_fao_evapotranspiration"][0])
        self.assertEqual(s.sources, ["Open-Meteo ERA5-Seamless"])
        self.assertIn("Open-Meteo.com", s.attribution)
        self.assertEqual(s.missing_days(), [])

    def test_errors(self):
        with self.assertRaisesRegex(om.OpenMeteoError, "Latitude must be"):
            om.parse_response({"error": True, "reason": "Latitude must be in range of -90 to 90°."})
        data = load()
        data["daily_units"]["wind_speed_10m_mean"] = "km/h"
        with self.assertRaisesRegex(om.OpenMeteoError, "units"):
            om.parse_response(data)
        data = load()
        del data["daily"]["shortwave_radiation_sum"]
        with self.assertRaisesRegex(om.OpenMeteoError, "shortwave_radiation_sum"):
            om.parse_response(data)

    def test_nulls_are_missing(self):
        data = load()
        data["daily"]["shortwave_radiation_sum"][4] = None
        s = om.parse_response(data)
        self.assertEqual(s.missing_days(), [date(2025, 7, 5)])


class TestFetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.calls = []
        with open(DATA, "rb") as fh:
            self.raw = fh.read()

    def fetcher(self, url):
        self.calls.append(url)
        return self.raw

    def test_cache_and_fetcher_required(self):
        args = (40.98, 27.51, date(2025, 7, 1), date(2025, 7, 5))
        om.fetch(*args, fetcher=self.fetcher, cache_dir=self.tmp)
        om.fetch(*args, fetcher=self.fetcher, cache_dir=self.tmp)
        self.assertEqual(len(self.calls), 1)
        with self.assertRaisesRegex(ValueError, "fetcher is required"):
            om.fetch(*args, cache_dir=None)

    def test_core_matches_open_meteo_et0(self):
        # Fed with Open-Meteo's own daily inputs, the core should be close to its FAO ET0
        s = om.parse_response(load())
        rows = eto_series.daily_eto_series(s.days, 40.98, s.elevation)
        ours = sum(r["ETo"] for r in rows)
        theirs = sum(s.reference_eto.values())
        self.assertAlmostEqual(ours / theirs, 1.0, delta=0.05)


if __name__ == "__main__":
    unittest.main()
