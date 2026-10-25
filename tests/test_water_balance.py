"""Unit tests for the Kc curve, effective rainfall and unit conversions."""

import unittest
from datetime import date

from fao56_cwr_mapper.core import water_balance as wb

# Arbitrary test crop: Kc 0.3 / 1.2 / 0.6, stages 10 / 20 / 30 / 20 days
CROP = dict(kc_ini=0.3, kc_mid=1.2, kc_end=0.6, l_ini=10, l_dev=20, l_mid=30, l_late=20)


class TestKcCurve(unittest.TestCase):
    def test_stage_boundaries(self):
        cases = {
            1: (0.3, "initial"), 10: (0.3, "initial"),
            11: (0.3 + 1 / 20 * 0.9, "development"),
            20: (0.75, "development"), 30: (1.2, "development"),
            31: (1.2, "mid"), 60: (1.2, "mid"),
            70: (0.9, "late"), 80: (0.6, "late"),
        }
        for day, (kc, stage) in cases.items():
            with self.subTest(day=day):
                got_kc, got_stage = wb.kc_for_day(day, **CROP)
                self.assertAlmostEqual(got_kc, kc, places=9)
                self.assertEqual(got_stage, stage)

    def test_outside_season(self):
        self.assertEqual(wb.kc_for_day(0, **CROP), (None, None))
        self.assertEqual(wb.kc_for_day(81, **CROP), (None, None))

    def test_series_dates(self):
        s = wb.kc_series(date(2026, 4, 1), **CROP)
        self.assertEqual(len(s), 80)
        self.assertEqual(s[0][0], date(2026, 4, 1))
        self.assertEqual(s[-1][0], date(2026, 6, 19))
        self.assertAlmostEqual(s[-1][1], 0.6)


class TestRainfallAndIrrigation(unittest.TestCase):
    def test_fixed_fraction(self):
        self.assertAlmostEqual(wb.effective_rainfall_fixed(10.0), 8.0)
        self.assertAlmostEqual(wb.effective_rainfall_fixed(10.0, 0.5), 5.0)
        self.assertEqual(wb.effective_rainfall_fixed(-1.0), 0.0)
        with self.assertRaises(ValueError):
            wb.effective_rainfall_fixed(10.0, 1.5)

    def test_net_irrigation_never_negative(self):
        self.assertAlmostEqual(wb.net_irrigation(5.0, 2.0), 3.0)
        self.assertEqual(wb.net_irrigation(2.0, 5.0), 0.0)

    def test_units(self):
        # 1 mm = 1 L/m2 = 1 m3/da = 10 m3/ha
        self.assertAlmostEqual(wb.depth_to_volume_m3(1.0, 1000.0), 1.0)
        self.assertAlmostEqual(wb.depth_to_volume_m3(500.0, 10000.0), 5000.0)
        self.assertEqual(wb.volume_per_decare(1.0), 1.0)
        self.assertEqual(wb.volume_per_hectare(1.0), 10.0)


if __name__ == "__main__":
    unittest.main()
