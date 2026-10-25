"""Tests for the run report (text and HTML)."""

import os
import tempfile
import unittest
from datetime import date

from fao56_cwr_mapper.core import report

META = {"layer": "fields <test>", "crs": "EPSG:32635", "ellipsoid": "EPSG:7030",
        "qgis_version": "3.44", "run_time": "2026-10-25 20:00", "plugin_version": "0.0.11"}
SETTINGS = {"pe_fraction": 0.8, "nir_period": "dekad", "efficiency": None, "user_kc_csv": "",
            "crop_source": "field 'crop'", "planting_source": "field 'planted'",
            "stage_source": "FAO-56 Table 11, region keyword 'Mediterranean'"}
ROWS = [
    {"feature": "Field A", "status": "ok", "crop": "Tomato", "stage": "x",
     "season_start": date(2025, 5, 1), "season_end": date(2025, 9, 22),
     "ETo": 926.6, "ETc": 888.1, "P": 73.5, "Pe": 58.8, "NIR": 829.3,
     "NIR_m3": 14939.4, "area_m2": 18013.6},
    {"feature": "Field B", "status": "ok", "crop": "Sunflower - irrigated", "stage": "y",
     "season_start": date(2025, 4, 15), "season_end": date(2025, 8, 22),
     "ETo": 812.8, "ETc": 716.5, "P": 67.9, "Pe": 54.4, "NIR": 663.4,
     "NIR_m3": 29874.1, "area_m2": 45034.1},
    {"feature": "Field <C>", "status": "error: crop 'Tomatoe' not found"},
]


class TestReport(unittest.TestCase):
    def test_totals(self):
        t = report.totals(ROWS)
        self.assertEqual((t["features"], t["computed"], t["failed"]), (3, 2, 1))
        self.assertAlmostEqual(t["area_ha"], 6.30477, places=4)
        self.assertAlmostEqual(t["volume_m3"], 44813.5)
        self.assertAlmostEqual(t["mean_nir_mm"], 44813.5 / 63047.7 * 1000)   # area weighted

    def test_text(self):
        text = report.build_text(META, SETTINGS, ROWS)
        for part in ("Inputs", "Method", "Climate data", "Summary", "Results per field",
                     "Warnings and errors", "Limitations", "References",
                     "Pe = 0.80 x P", "per dekad", "Eq. 66", "2025-04-15 to 2025-09-22",
                     "Field <C>: error: crop 'Tomatoe' not found", "Allen, R.G.",
                     "NASA Langley Research Center", "No soil water storage"):
            with self.subTest(part=part):
                self.assertIn(part, text)
        self.assertIn("44 814 m3", text)

    def test_daily_mode_and_efficiency(self):
        text = report.build_text(META, dict(SETTINGS, nir_period="daily", efficiency=0.75), ROWS)
        self.assertIn("per day: NIR = max(0, ETc - Pe)", text)
        self.assertIn("GIR = NIR / 0.75", text)

    def test_html_is_escaped(self):
        page = report.build_html(META, SETTINGS, ROWS)
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("Field &lt;C&gt;", page)
        self.assertIn("fields &lt;test&gt;", page)
        self.assertNotIn("Field <C>", page)
        self.assertEqual(page.count("<tr><td>"), 3)                 # one row per feature

    def test_write_by_extension(self):
        tmp = tempfile.mkdtemp()
        for name, start in (("r.html", "<!doctype html>"), ("r.txt", "FAO-56 Crop Water")):
            path = report.write_report(os.path.join(tmp, name), META, SETTINGS, ROWS)
            with open(path, encoding="utf-8") as fh:
                self.assertTrue(fh.read().startswith(start))

    def test_plugin_version_from_metadata(self):
        self.assertRegex(report.plugin_version(), r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
