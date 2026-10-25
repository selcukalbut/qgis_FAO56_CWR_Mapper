"""Tests for the FAO-56 Table 12 crop coefficient loader."""

import os
import tempfile
import unittest

from fao56_cwr_mapper.core import crop_table as ct


class TestKcTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.crops = ct.load_kc_table()

    def get(self, name):
        return ct.find_crop(self.crops, name)

    def test_all_values_numeric_and_plausible(self):
        for c in self.crops:
            for col in ct.KC_COLUMNS:
                v = getattr(c, col)
                with self.subTest(crop=c.name, col=col):
                    self.assertIsInstance(v, float)
                    self.assertTrue(0.1 <= v <= 1.4, v)

    def test_names_unique(self):
        names = [c.name.lower() for c in self.crops]
        self.assertEqual(len(names), len(set(names)))

    def test_book_values(self):
        # FAO-56 Table 12 as printed (pp. 110-114)
        cases = {
            "Tomato": (0.6, 1.15, 0.80),            # group Kc_ini, end = midpoint of 0.70-0.90
            "Potato": (0.5, 1.15, 0.75),
            "Sugar Cane": (0.40, 1.25, 0.75),
            "Walnut Orchard": (0.50, 1.10, 0.65),
            "Olives (40 to 60% ground coverage by canopy)": (0.65, 0.70, 0.70),
            "Peas - Dry/Seed": (0.5, 1.15, 0.30),   # author decision, see corrections
            "Cassava - year 1": (0.3, 0.80, 0.30),
        }
        for name, expected in cases.items():
            c = self.get(name)
            with self.subTest(crop=name):
                self.assertEqual((c.kc_ini, c.kc_mid, c.kc_end), expected)

    def test_footnote_ranges_split_into_variants(self):
        self.assertEqual(self.get("Maize, Field (grain) (field corn) - harvest at high grain moisture").kc_end, 0.60)
        self.assertEqual(self.get("Maize, Field (grain) (field corn) - grain dried in field").kc_end, 0.35)
        self.assertEqual(self.get("Sunflower - irrigated").kc_mid, 1.15)
        self.assertEqual(self.get("Sunflower - rainfed").kc_mid, 1.0)
        wheat = self.get("Winter Wheat - with frozen soils, hand harvested")
        self.assertEqual((wheat.kc_ini, wheat.kc_end), (0.4, 0.4))
        with self.assertRaises(KeyError):
            self.get("Sunflower")                  # unsplit row no longer offered

    def test_every_variant_rule_is_used(self):
        # Guards against a crop name typo in kc_range_variants.csv
        import csv
        with open(ct.RANGE_VARIANTS, newline="", encoding="utf-8") as fh:
            rules = list(csv.DictReader(fh))
        names = {c.name for c in self.crops}
        for r in rules:
            variant = ", ".join(p for p in (r["variant"], r["new_variant"]) if p)
            with self.subTest(rule=r["crop"] + " / " + variant):
                self.assertIn("{} - {}".format(r["crop"], variant), names)

    def test_unexplained_ranges_use_midpoint(self):
        expected = {"Tomato": ("kc_end", 0.80, (0.70, 0.90)),
                    "Cotton": ("kc_mid", 1.175, (1.15, 1.20)),
                    "Rice": ("kc_end", 0.75, (0.90, 0.60)),
                    "Sorghum - grain": ("kc_mid", 1.05, (1.00, 1.10)),
                    "Grazing Pasture - Rotated Grazing": ("kc_mid", 0.95, (0.85, 1.05))}
        for name, (col, mid, rng) in expected.items():
            c = self.get(name)
            with self.subTest(crop=name):
                self.assertAlmostEqual(getattr(c, col), mid)
                self.assertEqual(c.kc_range[col], rng)
                self.assertTrue(any("midpoint" in n for n in c.notes))

    def test_open_water_excluded(self):
        self.assertFalse([c for c in self.crops if c.crop.startswith("Open Water")])

    def test_user_override(self):
        tomato = self.get("Tomato")
        mine = tomato.with_values(kc_end=0.70)
        self.assertEqual(mine.kc_end, 0.70)
        self.assertEqual(tomato.kc_end, 0.80)      # original untouched
        self.assertIn("kc_end set by user to 0.7", mine.notes)


class TestUserKcCsv(unittest.TestCase):
    def write(self, text):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_load(self):
        path = self.write("crop,variant,kc_ini,kc_mid,kc_end\nSunflower,Thrace,0.35,1.10,0.40\n")
        c = ct.load_user_kc_csv(path)[0]
        self.assertEqual((c.name, c.kc_ini, c.kc_mid, c.kc_end), ("Sunflower - Thrace", 0.35, 1.10, 0.40))
        self.assertTrue(c.source.startswith("user table"))

    def test_bad_value(self):
        path = self.write("crop,kc_ini,kc_mid,kc_end\nX,0.3,high,0.4\n")
        with self.assertRaisesRegex(ValueError, "line 2"):
            ct.load_user_kc_csv(path)


if __name__ == "__main__":
    unittest.main()
