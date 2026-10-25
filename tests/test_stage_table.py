"""Tests for FAO-56 Table 11 stage lengths and the Table 11 / Table 12 crop mapping."""

import os
import tempfile
import unittest
from datetime import date

from fao56_cwr_mapper.core import crop_table as ct
from fao56_cwr_mapper.core import stage_table as st


class TestStageTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stages = st.load_stage_table()

    def rows(self, crop):
        return [s for s in self.stages if s.crop == crop]

    def test_book_values(self):
        # FAO-56 Table 11 as printed
        tomato = self.rows("Tomato")
        self.assertEqual(len(tomato), 5)
        self.assertEqual(tomato[4].lengths, (30, 40, 45, 30))
        self.assertEqual((tomato[4].plant_date, tomato[4].region), ("April/May", "Mediterranean"))
        olives = self.rows("Olives")[0]
        self.assertEqual((olives.lengths, olives.total_printed), ((30, 90, 60, 90), 270))
        maize = self.rows("Maize (sweet)")[4]          # Idaho row, book: late 10 (footnote 3)
        self.assertEqual(maize.l_late, 10)

    def test_alternatives_expanded(self):
        carrots = [s for s in self.rows("Carrots") if s.row == 1]
        self.assertEqual([(s.option, s.l_mid, s.total_matches) for s in carrots],
                         [("a", 50, False), ("b", 30, True)])
        spinach = [s for s in self.rows("Spinach") if s.row == 1]   # mid 15/25 paired with total 60/70
        self.assertEqual([(s.l_mid, s.total_printed, s.total_matches) for s in spinach],
                         [(15, 60, True), (25, 70, True)])
        peppers = [s for s in self.rows("Sweet peppers (bell)") if s.row == 1]
        self.assertEqual([(s.l_ini, s.total_matches) for s in peppers], [(25, False), (30, True)])

    def test_unusable_rows_skipped(self):
        self.assertEqual(self.rows("Alfalfa, total season"), [])
        self.assertEqual(self.rows("Grass Pasture"), [])

    def test_original_inconsistencies_are_noted(self):
        sorghum = self.rows("Sorghum")[0]
        self.assertFalse(sorghum.total_matches)
        self.assertTrue(any("checked in book" in n for n in sorghum.notes))
        unexplained = [s for s in self.stages if not s.total_matches and not s.notes]
        self.assertEqual(unexplained, [])


class TestCropMapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.crops = ct.load_kc_table()
        cls.stages = st.load_stage_table()
        cls.mapping = st.load_crop_mapping()

    def options(self, name):
        return st.stage_options(ct.find_crop(self.crops, name), self.stages, self.mapping)

    def test_every_rule_resolves(self):
        kc = {c.crop for c in self.crops}
        stage = {s.crop for s in self.stages}
        for r in self.mapping:
            with self.subTest(rule=r["kc_crop"] + " -> " + r["stage_crop"]):
                self.assertIn(r["kc_crop"], kc)
                self.assertIn(r["stage_crop"], stage)

    def test_every_table11_crop_is_reachable(self):
        used = {s.crop for c in self.crops for s in st.stage_options(c, self.stages, self.mapping)}
        self.assertEqual({s.crop for s in self.stages} - used, set())

    def test_name_differences(self):
        self.assertEqual({s.crop for s in self.options("Egg Plant")}, {"Egg plant"})
        self.assertEqual({s.crop for s in self.options("Sugar Beet")}, {"Sugarbeet"})
        self.assertEqual({s.crop for s in self.options("Brussel Sprouts")}, {"Crucifers"})
        self.assertEqual({s.crop for s in self.options("Barley")}, {"Barley/Oats/Wheat", "Grains (small)"})

    def test_variant_rules(self):
        fresh = self.options("Fababean (broad bean) - Fresh")
        self.assertEqual(sorted(s.variant for s in fresh), ["", "", "green"])
        self.assertEqual(sorted(s.variant for s in self.options("Fababean (broad bean) - Dry/Seed")),
                         ["", "", "dry"])
        self.assertEqual({s.crop for s in self.options("Onions - green")}, {"Onion (green)"})
        # split variants keep the mapping of the printed variant
        self.assertEqual(len(self.options("Winter Wheat - with frozen soils, hand harvested")), 3)
        self.assertEqual(len(self.options("Apples, Cherries, Pears - no ground cover, killing frost")), 3)

    def test_planting_months(self):
        cases = {"Apr/May": {4, 5}, "Mar-May": {3, 4, 5}, "Oct; Jan.": {1, 10}, "Sept": {9},
                 "Dec/Jan": {12, 1}, "Rainy": set(), "Apr; Sep/Oct": {4, 9, 10}}
        for text, months in cases.items():
            with self.subTest(text=text):
                self.assertEqual(st.planting_months(text), months)

    def test_select_by_region(self):
        opts = self.options("Sunflower - irrigated")
        chosen, note = st.select_stage_option(opts, "Mediterranean", date(2025, 4, 15))
        self.assertEqual(chosen.region, "Medit.; California")      # "Medit." abbreviation matched
        self.assertIsNone(note)

    def test_select_by_month_when_region_missing(self):
        opts = self.options("Maize, Field (grain) (field corn) - grain dried in field")
        chosen, note = st.select_stage_option(opts, "Mediterranean", date(2025, 4, 20))
        self.assertEqual(chosen.plant_date, "April")
        self.assertIn("no FAO-56 Table 11 example for region 'Mediterranean'", note)
        self.assertIn("Spain", note)                               # alternatives listed
        self.assertIn("Idaho", note)
        chosen, note = st.select_stage_option(opts, "Spain", date(2025, 4, 20))
        self.assertEqual((chosen.lengths, note), ((30, 40, 50, 30), None))

    def test_select_without_month_match(self):
        opts = self.options("Potato")
        chosen, note = st.select_stage_option(opts, "Mediterranean", date(2025, 3, 10))
        self.assertIs(chosen, opts[0])
        self.assertIn("no example for planting month March", note)

    def test_crop_without_table11_lengths(self):
        self.assertEqual(self.options("Garlic"), [])

    def test_season_kc_series(self):
        tomato = ct.find_crop(self.crops, "Tomato")
        stage = [s for s in self.options("Tomato") if s.region == "Mediterranean"][0]
        series = st.season_kc_series(tomato, stage, date(2026, 4, 15))
        self.assertEqual(len(series), 145)
        self.assertEqual(series[0][1:], (0.6, "initial"))
        self.assertEqual(series[100][1:], (1.15, "mid"))       # day 101: 30+40 < 101 <= 115
        self.assertAlmostEqual(series[-1][1], 0.80)            # Kc_end midpoint of 0.70-0.90


class TestUserStageCsv(unittest.TestCase):
    def write(self, text):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_load(self):
        path = self.write("crop,l_ini,l_dev,l_mid,l_late,plant_date,region\nGarlic,20,30,60,20,Nov,Thrace\n")
        s = st.load_user_stage_csv(path)[0]
        self.assertEqual((s.crop, s.lengths, s.total, s.region), ("Garlic", (20, 30, 60, 20), 130, "Thrace"))
        self.assertTrue(s.total_matches)

    def test_bad_value(self):
        path = self.write("crop,l_ini,l_dev,l_mid,l_late\nX,20,thirty,60,20\n")
        with self.assertRaisesRegex(ValueError, "line 2"):
            st.load_user_stage_csv(path)


if __name__ == "__main__":
    unittest.main()
