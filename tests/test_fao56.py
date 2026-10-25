"""Unit tests against the worked examples of FAO-56 (Allen et al., 1998).

Expected values are the published (rounded) numbers; tolerances follow the
number of decimals printed in the publication.
Run from the repository root:  python3 -m unittest discover -s tests -v
"""

import math
import unittest
from datetime import date

from fao56_cwr_mapper.core import fao56 as f


class TestAtmosphere(unittest.TestCase):
    def test_example_2_pressure_and_gamma(self):
        # Example 2: z = 1800 m -> P = 81.8 kPa, gamma = 0.054 kPa/degC
        p = f.atmospheric_pressure(1800)
        self.assertAlmostEqual(p, 81.8, delta=0.05)
        self.assertAlmostEqual(f.psychrometric_constant(p), 0.054, delta=0.0005)


class TestHumidity(unittest.TestCase):
    def test_table_2_3_saturation_vapour_pressure(self):
        # Annex 2, Table 2.3
        for t, e in ((1.0, 0.657), (15.0, 1.705), (17.0, 1.938), (24.5, 3.075)):
            self.assertAlmostEqual(f.saturation_vapour_pressure(t), e, delta=0.0005)

    def test_table_2_4_slope(self):
        # Annex 2, Table 2.4
        for t, d in ((1.0, 0.047), (20.0, 0.145), (30.0, 0.243)):
            self.assertAlmostEqual(f.slope_vapour_pressure_curve(t), d, delta=0.0005)

    def test_example_3_mean_es(self):
        # Example 3: Tmax 24.5, Tmin 15 -> es = 2.39 kPa
        self.assertAlmostEqual(f.mean_saturation_vapour_pressure(24.5, 15.0), 2.39, delta=0.005)

    def test_example_5_ea_from_rh(self):
        # Example 5: Tmax 25, Tmin 18, RHmax 82 %, RHmin 54 %
        self.assertAlmostEqual(f.actual_vapour_pressure_from_rhmin_rhmax(25, 18, 82, 54), 1.70, delta=0.005)
        self.assertAlmostEqual(f.actual_vapour_pressure_from_rhmax(18, 82), 1.69, delta=0.005)
        self.assertAlmostEqual(f.actual_vapour_pressure_from_rhmean(25, 18, 68), 1.78, delta=0.005)


class TestRadiation(unittest.TestCase):
    def test_example_8_ra(self):
        # Example 8: 20 deg S, 3 September (J = 246)
        j = 246
        self.assertEqual(f.day_of_year(date(2026, 9, 3)), j)
        self.assertAlmostEqual(f.inverse_relative_distance(j), 0.985, delta=0.0005)
        self.assertAlmostEqual(f.solar_declination(j), 0.120, delta=0.0005)
        ws = f.sunset_hour_angle(math.radians(-20), f.solar_declination(j))
        self.assertAlmostEqual(ws, 1.527, delta=0.0005)
        self.assertAlmostEqual(f.extraterrestrial_radiation(-20, j), 32.2, delta=0.05)

    def test_example_9_daylight_hours(self):
        self.assertAlmostEqual(f.daylight_hours(-20, 246), 11.7, delta=0.05)

    def test_example_10_rs_from_sunshine(self):
        # Example 10: Rio de Janeiro 22 deg 54' S, 15 May (J = 135), n = 7.1 h
        lat = -(22 + 54 / 60)
        ra = f.extraterrestrial_radiation(lat, 135)
        n_max = f.daylight_hours(lat, 135)
        self.assertAlmostEqual(ra, 25.1, delta=0.05)
        self.assertAlmostEqual(n_max, 10.9, delta=0.05)
        self.assertAlmostEqual(f.solar_radiation_from_sunshine(7.1, n_max, ra), 14.5, delta=0.05)

    def test_example_11_net_radiation(self):
        # Example 11: Rio, Tmax 25.1, Tmin 19.1, ea 2.1, Rs 14.5, Ra 25.1, sea level
        rso = f.clear_sky_radiation(25.1, 0)
        rnl = f.net_longwave_radiation(25.1, 19.1, 2.1, 14.5, rso)
        rns = f.net_shortwave_radiation(14.5)
        self.assertAlmostEqual(rso, 18.8, delta=0.05)
        self.assertAlmostEqual(rnl, 3.5, delta=0.05)
        # Publication prints 0.77 x 14.5 = 11.165 as 11.1 (truncated)
        self.assertAlmostEqual(rns, 11.1, delta=0.07)
        self.assertAlmostEqual(f.net_radiation(rns, rnl), 7.6, delta=0.05)

    def test_polar_latitudes_do_not_fail(self):
        self.assertAlmostEqual(f.extraterrestrial_radiation(80, 355), 0.0, delta=1e-9)  # polar night
        self.assertGreater(f.extraterrestrial_radiation(80, 172), 0.0)                 # polar day
        self.assertAlmostEqual(f.daylight_hours(80, 172), 24.0, delta=1e-9)


class TestWind(unittest.TestCase):
    def test_example_14_wind_2m(self):
        # Example 14: 3.2 m/s at 10 m -> 2.4 m/s at 2 m
        self.assertAlmostEqual(f.wind_speed_2m(3.2, 10), 2.4, delta=0.05)


class TestExample17DailyETo(unittest.TestCase):
    """Example 17: Brussels, 6 July, 50 deg 48' N, 100 m."""

    def setUp(self):
        self.lat = 50 + 48 / 60
        self.day = date(2026, 7, 6)
        tmax, tmin = 21.5, 12.3
        ea = f.actual_vapour_pressure_from_rhmin_rhmax(tmax, tmin, 84, 63)
        u2 = f.wind_speed_2m(10 / 3.6, 10)
        j = f.day_of_year(self.day)
        ra = f.extraterrestrial_radiation(self.lat, j)
        rs = f.solar_radiation_from_sunshine(9.25, f.daylight_hours(self.lat, j), ra)
        self.r = f.daily_eto(self.day, self.lat, 100, tmax, tmin, u2, ea, rs)

    def test_intermediate_values(self):
        r = self.r
        expected = {
            "J": (187, 0), "t_mean": (16.9, 0.05), "delta": (0.122, 0.0005),
            "P": (100.1, 0.05), "gamma": (0.0666, 0.00005), "es": (1.997, 0.0005),
            "ea": (1.409, 0.0005), "vpd": (0.589, 0.0005), "u2": (2.078, 0.0005),
            "Ra": (41.09, 0.005), "Rs": (22.07, 0.005), "Rso": (30.90, 0.005),
            # Rns: publication multiplies the already-rounded Rs (22.07)
            "Rns": (16.99, 0.01), "Rnl": (3.71, 0.005), "Rn": (13.28, 0.005),
        }
        for key, (value, tol) in expected.items():
            with self.subTest(key=key):
                self.assertAlmostEqual(r[key], value, delta=tol)

    def test_eto(self):
        self.assertAlmostEqual(self.r["ETo"], 3.9, delta=0.05)


if __name__ == "__main__":
    unittest.main()
