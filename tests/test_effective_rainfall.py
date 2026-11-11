"""Effective rainfall: USDA SCS methods (CROPWAT form and NEH Part 623).

NEH values: USDA NRCS National Engineering Handbook Part 623 Chapter 2 (1993),
Eq. 2-84/2-85, the worked example on p. 2-147 and Table 2-43 (D = 3 in).
"""

import unittest
from datetime import date, timedelta

from fao56_cwr_mapper.core import field_balance
from fao56_cwr_mapper.core import water_balance as wb
from fao56_cwr_mapper.core.crop_table import CropKc
from fao56_cwr_mapper.core.stage_table import StageLengths

IN = wb.MM_PER_INCH


class TestCropwat(unittest.TestCase):
    def test_formula(self):
        self.assertAlmostEqual(wb.effective_rainfall_usda_cropwat(100), 84.0)       # 100 (125-20)/125
        self.assertAlmostEqual(wb.effective_rainfall_usda_cropwat(250), 150.0)
        self.assertAlmostEqual(wb.effective_rainfall_usda_cropwat(250.001), 150.0, places=3)  # continuous
        self.assertAlmostEqual(wb.effective_rainfall_usda_cropwat(300), 155.0)
        self.assertEqual(wb.effective_rainfall_usda_cropwat(0), 0.0)

    def test_dekad_equals_decade_form(self):
        # 10 days of a 30-day month: factor 3, i.e. Pe = P (125 - 0.6 P) / 125
        spec = wb.EffectiveRainfall(wb.PE_USDA_CROPWAT)
        self.assertAlmostEqual(spec.period(30.0, 0, 10, 30), 30 * (125 - 0.6 * 30) / 125)


class TestNeh(unittest.TestCase):
    def test_worked_example(self):
        # ETc 7.6 in, Pt 4.7 in: Eq. 2-84 gives 3.70 in at D = 3 in; with D = 2 in, SF = 0.93 -> 3.44 in
        base = wb.effective_rainfall_usda_neh(4.7 * IN, 7.6 * IN, storage_mm=3 * IN) / IN
        self.assertAlmostEqual(base, 3.70, delta=0.01)
        self.assertAlmostEqual(wb.soil_storage_factor(2.0), 0.93, delta=0.01)
        pe = wb.effective_rainfall_usda_neh(4.7 * IN, 7.6 * IN, storage_mm=2 * IN) / IN
        self.assertAlmostEqual(pe, 3.44, delta=0.04)          # Eq. 2-85 gives SF 0.922

    def test_storage_factors_table_2_43(self):
        table = {0.75: 0.72, 1.0: 0.77, 1.5: 0.86, 2.0: 0.93, 2.5: 0.97, 3.0: 1.00,
                 4.0: 1.02, 5.0: 1.04, 6.0: 1.06, 7.0: 1.07}
        for d, sf in table.items():
            with self.subTest(D=d):
                self.assertAlmostEqual(wb.soil_storage_factor(d), sf, delta=0.015)

    def test_table_2_43(self):
        # (Pt in, ETc in): Pe in, D = 3 in. The table caps Pe at P (1.00 at Pt 1.0, ETc 10)
        # but not at ETc (1.73 at ETc 1.0); its note and the text limit Pe to the lesser of
        # P and ETc, which the plugin applies.
        table = {(0.5, 0.0): 0.28, (0.5, 5.0): 0.38, (1.0, 3.0): 0.70, (2.0, 5.0): 1.51,
                 (3.0, 1.0): 1.73, (4.0, 7.0): 3.12, (5.5, 2.0): 3.10, (8.0, 10.0): 6.68,
                 (2.5, 9.0): 2.30}
        for (pt, etc), pe in table.items():
            with self.subTest(Pt=pt, ETc=etc):
                self.assertAlmostEqual(wb.usda_neh_base_inch(pt, etc), pe, delta=0.011)
        # limited: 1.73 -> ETc 1.0; P 1.0 at ETc 10 (1.04 from Eq. 2-84) -> table 1.00 = P
        self.assertAlmostEqual(wb.effective_rainfall_usda_neh(3 * IN, 1 * IN, 3 * IN) / IN, 1.0)
        self.assertAlmostEqual(wb.effective_rainfall_usda_neh(1 * IN, 10 * IN, 3 * IN) / IN, 1.0)

    def test_limits(self):
        self.assertEqual(wb.effective_rainfall_usda_neh(0, 100), 0.0)
        self.assertLessEqual(wb.effective_rainfall_usda_neh(200, 50), 50.0)     # not above ETc
        self.assertLessEqual(wb.effective_rainfall_usda_neh(5, 250), 5.0)       # not above P
        with self.assertRaises(ValueError):
            wb.EffectiveRainfall(wb.PE_USDA_NEH, storage_mm=0)
        with self.assertRaises(ValueError):
            wb.EffectiveRainfall("scs")


class TestFieldBalance(unittest.TestCase):
    CROP = CropKc("t", "Test", "", 1.0, 1.0, 1.0)
    STAGE = StageLengths("Test", "", 1, 10, 10, 10, 10, 40)

    def rows(self, start, n, rain):
        return [{"day": start + timedelta(days=k), "ETo": 5.0, "precip": rain(k), "missing": False,
                 "estimated": []} for k in range(n)]

    def run_balance(self, rows, start, spec, period=field_balance.NIR_DEKAD):
        return field_balance.field_water_balance(rows, self.CROP, self.STAGE, start, nir_period=period,
                                                 effective_rainfall=spec, today=date(2026, 1, 1))

    def test_dekad_pe_shared_by_rainfall(self):
        start = date(2025, 6, 1)                      # June: 30 days, dekads of 10 days
        rows = self.rows(start, 40, lambda k: 20.0 if k % 10 == 0 else 0.0)
        spec = wb.EffectiveRainfall(wb.PE_USDA_CROPWAT)
        r = self.run_balance(rows, start, spec)
        d1 = r["dekad"][0]
        self.assertAlmostEqual(d1["Pe"], 20 * (125 - 0.6 * 20) / 125)
        self.assertAlmostEqual(d1["NIR"], 50.0 - d1["Pe"])
        self.assertAlmostEqual(r["daily"][0]["Pe"], d1["Pe"])       # all on the rainy day
        self.assertEqual(r["daily"][1]["Pe"], 0.0)
        self.assertEqual(r["summary"]["pe_method"], wb.PE_USDA_CROPWAT)
        self.assertIsNone(r["summary"]["pe_fraction"])
        # daily NIR: rain only offsets the rainy day
        daily = self.run_balance(rows, start, spec, field_balance.NIR_DAILY)
        self.assertAlmostEqual(daily["dekad"][0]["NIR"], 45.0)

    def test_eleven_day_dekad(self):
        start = date(2025, 7, 21)                     # 21-31 July: 11 days, month of 31
        rows = self.rows(start, 40, lambda k: 3.0)
        spec = wb.EffectiveRainfall(wb.PE_USDA_NEH, storage_mm=75)
        d3 = self.run_balance(rows, start, spec)["dekad"][0]
        self.assertEqual(d3["days"], 11)
        self.assertAlmostEqual(d3["Pe"], wb.effective_rainfall_usda_neh(33 * 31 / 11, 55 * 31 / 11, 75) * 11 / 31)

    def test_fixed_default_unchanged(self):
        start = date(2025, 6, 1)
        rows = self.rows(start, 40, lambda k: 2.0)
        r = self.run_balance(rows, start, None)
        self.assertAlmostEqual(r["summary"]["Pe_mm"], 0.8 * 80)
        self.assertEqual(r["summary"]["pe_fraction"], 0.8)


if __name__ == "__main__":
    unittest.main()
