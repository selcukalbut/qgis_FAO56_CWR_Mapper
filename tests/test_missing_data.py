"""FAO-56 procedures for missing climatic data (Chapter 3), against the worked examples."""

import math
import unittest
from datetime import date

from fao56_cwr_mapper.core import eto_series as es
from fao56_cwr_mapper.core import fao56
from fao56_cwr_mapper.core.climate import DailyClimate

LYON = 45 + 43 / 60          # 45 deg 43' N, 200 m


def record(**kw):
    base = dict(day=date(2025, 7, 15), tmax=None, tmin=None, tdew=None, rh=None,
                u2=None, rs=None, precip=0.0)
    base.update(kw)
    return DailyClimate(**base)


class TestRadiationFromTemperature(unittest.TestCase):
    def test_example_15_interior(self):
        # Lyon, July (J = 196): Ra = 40.6, Rs = 0.16 sqrt(26.6 - 14.8) Ra = 22.3 MJ m-2 day-1
        ra = fao56.extraterrestrial_radiation(LYON, 196)
        self.assertAlmostEqual(ra, 40.6, delta=0.05)
        self.assertAlmostEqual(fao56.solar_radiation_from_temperature(26.6, 14.8, ra), 22.3, delta=0.05)

    def test_example_16_coastal(self):
        # Bangkok 13 deg 44' N, 15 April (J = 105), coastal kRs = 0.19: Ra = 38.1, Rs = 21.9
        ra = fao56.extraterrestrial_radiation(13 + 44 / 60, 105)
        self.assertAlmostEqual(ra, 38.1, delta=0.05)
        self.assertAlmostEqual(fao56.solar_radiation_from_temperature(34.8, 25.6, ra, krs=0.19),
                               21.9, delta=0.05)

    def test_negative_range_gives_zero(self):
        self.assertEqual(fao56.solar_radiation_from_temperature(10, 12, 30.0), 0.0)


class TestExample20OnlyTemperature(unittest.TestCase):
    """Example 20: ETo with only Tmax and Tmin (Lyon, July, 200 m) -> 4.56 mm/day."""

    def setUp(self):
        rec = record(tmax=26.6, tmin=14.8)
        self.row = es.daily_eto_series([rec], LYON, 200, estimation=es.Estimation())[0]

    def test_intermediate_values(self):
        r = self.row
        for key, value, tol in (("ea", 1.68, 0.005), ("es", 2.58, 0.005), ("delta", 0.150, 0.0005),
                                ("gamma", 0.066, 0.0005), ("Ra", 40.55, 0.01), ("Rs", 22.29, 0.05),
                                ("Rso", 30.58, 0.01), ("Rns", 17.16, 0.05), ("Rnl", 3.68, 0.05),
                                ("Rn", 13.48, 0.05), ("u2", 2.0, 0)):
            with self.subTest(key=key):
                self.assertAlmostEqual(r[key], value, delta=tol)

    def test_eto(self):
        self.assertAlmostEqual(self.row["ETo"], 4.56, delta=0.02)

    def test_estimates_are_listed(self):
        self.assertEqual(self.row["estimated"], [es.EST_EA, es.EST_RS, es.EST_U2])
        self.assertEqual((self.row["ea_method"], self.row["rs_method"]), (es.EA_TMIN, es.RS_TEMPERATURE))

    def test_without_estimation_the_day_is_missing(self):
        row = es.daily_eto_series([record(tmax=26.6, tmin=14.8)], LYON, 200)[0]
        self.assertTrue(row["missing"])
        self.assertIsNone(row["ETo"])

    def test_estimation_can_be_limited(self):
        only_wind = es.Estimation(humidity=False, radiation=False)
        row = es.daily_eto_series([record(tmax=26.6, tmin=14.8, rh=74, rs=22.29)], LYON, 200,
                                  estimation=only_wind)[0]
        self.assertEqual(row["estimated"], [es.EST_U2])
        self.assertFalse(row["missing"])


class TestMeasuredInputsComeFirst(unittest.TestCase):
    def test_humidity_order(self):
        # Example 5 values: Tmax 25, Tmin 18, RHmax 82, RHmin 54
        cases = [(dict(tdew=17.0, rhmax=82, rhmin=54, rh=68), es.EA_TDEW, 1.938),
                 (dict(rhmax=82, rhmin=54, rh=68), es.EA_RHMAX_RHMIN, 1.70),
                 (dict(rhmax=82), es.EA_RHMAX, 1.69),
                 (dict(rh=68), es.EA_RHMEAN, 1.78)]
        for kw, method, ea in cases:
            with self.subTest(method=method):
                rec = record(tmax=25, tmin=18, **kw)
                value, used = es.actual_vapour_pressure(rec, es.Estimation())
                self.assertEqual(used, method)
                self.assertAlmostEqual(value, ea, delta=0.005)

    def test_sunshine_before_temperature(self):
        # Example 10: Rio de Janeiro 22 deg 54' S, 15 May, n = 7.1 h -> Rs = 14.5
        rec = record(day=date(2025, 5, 15), tmax=25.1, tmin=19.1, sunshine=7.1)
        rs, method = es.solar_radiation(rec, -(22 + 54 / 60), es.Estimation())
        self.assertEqual(method, es.RS_SUNSHINE)
        self.assertAlmostEqual(rs, 14.5, delta=0.05)

    def test_measured_radiation_wins(self):
        rec = record(tmax=26.6, tmin=14.8, rs=25.0, sunshine=3.0)
        self.assertEqual(es.solar_radiation(rec, LYON, es.Estimation()), (25.0, es.RS_MEASURED))


class TestCalmWindLimit(unittest.TestCase):
    def test_u2_at_least_half_a_metre_per_second(self):
        calm = fao56.daily_eto(date(2025, 7, 15), LYON, 200, 26.6, 14.8, 0.1, 1.68, 22.29)
        limit = fao56.daily_eto(date(2025, 7, 15), LYON, 200, 26.6, 14.8, 0.5, 1.68, 22.29)
        self.assertEqual(calm["u2"], 0.5)
        self.assertTrue(math.isclose(calm["ETo"], limit["ETo"]))


if __name__ == "__main__":
    unittest.main()
