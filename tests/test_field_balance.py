"""Tests for the field water balance and the point pipeline (offline)."""

import os
import unittest
from datetime import date, timedelta

from fao56_cwr_mapper import pipeline
from fao56_cwr_mapper.core import field_balance as fb
from fao56_cwr_mapper.core.crop_table import CropKc
from fao56_cwr_mapper.core.stage_table import StageLengths

TODAY = date(2026, 10, 25)
CROP = CropKc("test", "Test crop", "", 0.5, 1.0, 0.5)
STAGE = StageLengths("Test crop", "", 1, 10, 10, 10, 10, 40)
PLANT = date(2025, 7, 1)        # season 1 Jul - 9 Aug 2025


def climate(eto=5.0, rain=None, drop=()):
    """Constant ETo, dry except for rain {date: mm}; days in drop have no ETo."""
    rain = rain or {}
    rows = []
    for k in range(40):
        d = PLANT + timedelta(days=k)
        rows.append({"day": d, "ETo": None if d in drop else eto, "precip": rain.get(d, 0.0)})
    return rows


class TestFieldBalance(unittest.TestCase):
    def test_dry_season_by_hand(self):
        # Kc sum = 10*0.5 + (5 + 0.05*55) + 10*1.0 + (10 - 0.05*55) = 30 -> ETc = 150 mm
        r = fb.field_water_balance(climate(), CROP, STAGE, PLANT, area_m2=10000, today=TODAY)
        s = r["summary"]
        self.assertAlmostEqual(s["ETo_mm"], 200.0)
        self.assertAlmostEqual(s["ETc_mm"], 150.0)
        self.assertAlmostEqual(s["NIR_mm"], 150.0)
        self.assertAlmostEqual(s["NIR_m3"], 1500.0)              # 150 mm on 1 ha
        self.assertAlmostEqual(s["NIR_m3_per_da"], 150.0)
        self.assertAlmostEqual(s["NIR_m3_per_ha"], 1500.0)
        self.assertEqual((s["season_start"], s["season_end"], s["season_days"]),
                         (date(2025, 7, 1), date(2025, 8, 9), 40))
        self.assertEqual(s["missing_days"], 0)
        self.assertEqual(s["warnings"], [])

    def test_daily_vs_dekad_rain(self):
        # 20 mm on 25 July (mid season, ETc 5 mm/day): Pe = 16 mm
        wet = climate(rain={date(2025, 7, 25): 20.0})
        daily = fb.field_water_balance(wet, CROP, STAGE, PLANT, nir_period=fb.NIR_DAILY,
                                       today=TODAY)["summary"]
        dekad = fb.field_water_balance(wet, CROP, STAGE, PLANT, nir_period=fb.NIR_DEKAD,
                                       today=TODAY)["summary"]
        default = fb.field_water_balance(wet, CROP, STAGE, PLANT, today=TODAY)["summary"]
        self.assertAlmostEqual(daily["Pe_mm"], 16.0)
        self.assertAlmostEqual(daily["NIR_mm"], 145.0)          # only that day's 5 mm offset
        self.assertAlmostEqual(dekad["NIR_mm"], 134.0)          # full 16 mm offset in the dekad
        self.assertEqual(default["nir_period"], fb.NIR_DEKAD)   # CROPWAT-like default
        self.assertAlmostEqual(default["NIR_mm"], 134.0)

    def test_dekads_and_months(self):
        r = fb.field_water_balance(climate(), CROP, STAGE, PLANT, today=TODAY)
        self.assertEqual([p["period"] for p in r["dekad"]],
                         ["2025-07-D1", "2025-07-D2", "2025-07-D3", "2025-08-D1"])
        self.assertEqual([p["days"] for p in r["dekad"]], [10, 10, 11, 9])
        self.assertAlmostEqual(sum(p["NIR"] for p in r["month"]), 150.0)
        self.assertEqual(r["summary"]["peak_dekad"], "2025-07-D3")  # mid season, 11 days

    def test_missing_day(self):
        r = fb.field_water_balance(climate(drop={date(2025, 7, 5)}), CROP, STAGE, PLANT, today=TODAY)
        s = r["summary"]
        self.assertEqual(s["missing_days"], 1)
        self.assertIsNone(r["dekad"][0]["NIR"])                 # incomplete dekad has no NIR
        self.assertAlmostEqual(s["NIR_mm"], 150.0 - 5 * 0.5 * 10)
        self.assertTrue(any("incomplete" in w for w in s["warnings"]))

    def test_future_season_warning(self):
        late = date(2026, 10, 1)
        r = fb.field_water_balance([], CROP, STAGE, late, today=TODAY)
        self.assertEqual(r["summary"]["missing_days"], 40)
        self.assertTrue(any("after today" in w for w in r["summary"]["warnings"]))

    def test_gross_requirement(self):
        s = fb.field_water_balance(climate(), CROP, STAGE, PLANT, efficiency=0.75,
                                   today=TODAY)["summary"]
        self.assertAlmostEqual(s["GIR_mm"], 200.0)
        with self.assertRaises(ValueError):
            fb.field_water_balance(climate(), CROP, STAGE, PLANT, efficiency=1.5)


class TestPipeline(unittest.TestCase):
    def fetcher(self, url):
        path = os.path.join(os.path.dirname(__file__), "data", "power_tekirdag_20250701_05.json")
        with open(path, "rb") as fh:
            return fh.read()

    def test_run_field_with_recorded_power_data(self):
        stage = StageLengths("Test crop", "", 1, 1, 1, 2, 1, 5)      # 1-5 July 2025
        r = pipeline.run_field(40.98, 27.51, CROP, stage, PLANT, area_m2=1000,
                               fetcher=self.fetcher, today=TODAY)
        s = r["summary"]
        self.assertEqual(s["missing_days"], 0)
        self.assertEqual(s["elevation_m"], 98.23)                   # POWER grid elevation
        self.assertIn("MERRA2", s["climate_source"])
        self.assertEqual(s["climate_api_version"], "v2.10.1")
        self.assertEqual(s["climate_sources"], ["MERRA2", "SYN1DEG", "POWER"])
        self.assertEqual(s["stage_lengths"], (1, 1, 2, 1))
        self.assertAlmostEqual(s["ETc_mm"], sum(d["Kc"] * d["ETo"] for d in r["daily"]))
        self.assertAlmostEqual(s["NIR_mm"], s["ETc_mm"])           # no rain 1-5 July
        self.assertAlmostEqual(s["NIR_m3"], s["NIR_mm"])            # 1000 m2 = 1 da

    def test_future_planting_rejected(self):
        with self.assertRaises(ValueError):
            pipeline.run_field(40.98, 27.51, CROP, STAGE, date(2026, 11, 1),
                               fetcher=self.fetcher, today=TODAY)


if __name__ == "__main__":
    unittest.main()
