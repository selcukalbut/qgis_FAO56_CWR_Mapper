"""Tests for Thiessen weighting of station ETo and rainfall."""

import unittest
from datetime import date, timedelta

from fao56_cwr_mapper import pipeline
from fao56_cwr_mapper.climate_sources import station_csv as sc
from fao56_cwr_mapper.core import weighting
from fao56_cwr_mapper.core.crop_table import CropKc
from fao56_cwr_mapper.core.stage_table import StageLengths

D1, D2, D3 = date(2025, 7, 1), date(2025, 7, 2), date(2025, 7, 3)


def row(day, eto, precip, estimated=()):
    return {"day": day, "ETo": eto, "precip": precip, "missing": eto is None,
            "estimated": list(estimated)}


class TestCombine(unittest.TestCase):
    def test_normalise(self):
        self.assertEqual(weighting.normalise_weights([("A", 3), ("B", 1), ("C", 0)]),
                         [("A", 0.75), ("B", 0.25)])
        with self.assertRaises(ValueError):
            weighting.normalise_weights([("A", 0)])

    def test_weighted_means_and_reweighting(self):
        a = [row(D1, 4.0, 0.0), row(D2, 4.0, 0.0), row(D3, None, None)]
        b = [row(D1, 6.0, 10.0, ["u2 = 2 m/s"]), row(D2, None, 8.0), row(D3, None, None)]
        out = weighting.combine_eto_rows([(0.75, a), (0.25, b)])
        d1, d2, d3 = out
        self.assertAlmostEqual(d1["ETo"], 4.5)                 # 0.75*4 + 0.25*6
        self.assertAlmostEqual(d1["precip"], 2.5)              # 0.75*0 + 0.25*10
        self.assertEqual((d1["reweighted"], d1["stations"], d1["estimated"]), (False, 2, ["u2 = 2 m/s"]))
        self.assertAlmostEqual(d2["ETo"], 4.0)                 # B missing: A alone
        self.assertAlmostEqual(d2["precip"], 2.0)              # both have rain: 0.75*0 + 0.25*8
        self.assertTrue(d2["reweighted"])
        self.assertTrue(d3["missing"])
        self.assertIsNone(d3["ETo"])

    def test_station_without_a_row_is_reweighted(self):
        out = weighting.combine_eto_rows([(0.5, [row(D1, 4.0, 1.0)]), (0.5, [])])
        self.assertEqual((out[0]["ETo"], out[0]["precip"], out[0]["reweighted"]), (4.0, 1.0, True))


def station_series(sid, tmax, elevation, days=40):
    lines = ["date,tmax,tmin,tdew,u2,rs,precip"]
    for k in range(days):
        lines.append("{},{},18,14,2,25,{}".format(D1 + timedelta(days=k), tmax, 1.0 if k % 7 == 0 else 0))
    recs = sc.read_station_csv("\n".join(lines) + "\n")[sc.SINGLE_STATION].days
    return sc.StationSeries(sid, 40.98, 27.51, elevation, recs)


class TestWeightedField(unittest.TestCase):
    CROP = CropKc("t", "Test", "", 0.5, 1.0, 0.5)
    STAGE = StageLengths("Test", "", 1, 10, 10, 10, 10, 40)
    TODAY = date(2026, 11, 11)

    def run_weighted(self, parts):
        return pipeline.run_field_weighted(40.98, 27.51, self.CROP, self.STAGE, D1, parts,
                                           today=self.TODAY)["summary"]

    def test_identical_stations_equal_single_station(self):
        a, b = station_series("A", 30, 50), station_series("B", 30, 50)
        weighted = self.run_weighted([(0.7, a), (0.3, b)])
        single = pipeline.run_field(40.98, 27.51, self.CROP, self.STAGE, D1, today=self.TODAY,
                                    series=a)["summary"]
        for key in ("ETo_mm", "ETc_mm", "P_mm", "NIR_mm"):
            with self.subTest(key=key):
                self.assertAlmostEqual(weighted[key], single[key], places=9)

    def test_weights_and_label(self):
        cool, hot = station_series("A", 26, 0), station_series("B", 34, 200)
        s = self.run_weighted([(3, cool), (1, hot)])            # weights are normalised
        only_cool = self.run_weighted([(1, cool)])
        only_hot = self.run_weighted([(1, hot)])
        self.assertAlmostEqual(s["ETo_mm"], 0.75 * only_cool["ETo_mm"] + 0.25 * only_hot["ETo_mm"], places=9)
        self.assertAlmostEqual(s["elevation_m"], 50.0)
        self.assertEqual(s["climate_source"], "Thiessen-weighted stations: A 75 %, B 25 %")
        self.assertEqual(s["reweighted_days"], 0)


if __name__ == "__main__":
    unittest.main()
