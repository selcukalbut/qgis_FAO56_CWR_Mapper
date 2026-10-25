"""Crop development stage lengths from FAO-56 Table 11, linked to Table 12 crops.

data/fao56_table11_stage_lengths.csv holds Table 11 as printed (book-checked).
Each row is an example for one planting date and region, so a crop usually
has several options and the user picks the one closest to local conditions.

- Values printed as alternatives ("50/30") become separate options. When the
  printed total also has alternatives ("60/70") they are paired in order.
  An option whose stages add up to the printed total is marked as matching.
- Rows without usable lengths ("var.", "--": alfalfa total season, grass
  pasture) are left out.
- data/crop_mapping.csv links Table 12 (Kc) crop names to Table 11 crop names,
  which differ in the publication (e.g. "Egg Plant" / "Egg plant").
"""

import csv
import os
import re

from . import water_balance
from .crop_table import DATA_DIR

STAGE_TABLE = os.path.join(DATA_DIR, "fao56_table11_stage_lengths.csv")
CROP_MAPPING = os.path.join(DATA_DIR, "crop_mapping.csv")
STAGE_COLUMNS = ("l_ini", "l_dev", "l_mid", "l_late")
NO_VARIANT = "(none)"


class StageLengths:
    """One set of stage lengths (days) with its planting date and region."""

    def __init__(self, crop, variant, row, l_ini, l_dev, l_mid, l_late, total_printed,
                 plant_date="", region="", option="", notes=None, source="FAO-56 Table 11"):
        self.crop = crop
        self.variant = variant
        self.row = row
        self.l_ini = l_ini
        self.l_dev = l_dev
        self.l_mid = l_mid
        self.l_late = l_late
        self.total_printed = total_printed
        self.plant_date = plant_date
        self.region = region
        self.option = option          # "a" / "b" for alternatives printed as "x/y"
        self.notes = notes or []
        self.source = source

    @property
    def lengths(self):
        return (self.l_ini, self.l_dev, self.l_mid, self.l_late)

    @property
    def total(self):
        return sum(self.lengths)

    @property
    def total_matches(self):
        return self.total_printed is None or self.total == self.total_printed

    @property
    def label(self):
        parts = [self.crop + (" - " + self.variant if self.variant else ""),
                 self.plant_date, self.region]
        text = ", ".join(p for p in parts if p)
        if self.option:
            text += " (option {})".format(self.option)
        return "{} [{} days]".format(text, self.total)

    def __repr__(self):
        return "StageLengths({!r}, {})".format(self.label, self.lengths)


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _alternatives(text):
    return [int(x) for x in text.split("/")]


def load_stage_table(path=STAGE_TABLE):
    """List of StageLengths in table order (alternatives expanded)."""
    out = []
    for row in _read_csv(path):
        cells = [row[c] for c in STAGE_COLUMNS] + [row["total"]]
        if not all(re.match(r"^\d+(/\d+)?$", c) for c in cells):
            continue                                   # "var.", "--"
        alts = [_alternatives(c) for c in cells]
        n = max(len(a) for a in alts)
        base_notes = [row["correction"]] if row["correction"] else []
        for i in range(n):
            pick = [a[i] if len(a) > 1 else a[0] for a in alts]
            notes = list(base_notes)
            option = ""
            if n > 1:
                option = "ab"[i]
                notes.append("printed as " + " | ".join(cells) + "; option " + option)
            s = StageLengths(row["crop"], row["variant"], int(row["row"]), *pick,
                             plant_date=row["plant_date"], region=row["region"],
                             option=option, notes=notes)
            if not s.total_matches and not row["correction"]:
                s.notes.append("stages add up to {} but printed total is {}".format(
                    s.total, s.total_printed))
            out.append(s)
    return out


def load_crop_mapping(path=CROP_MAPPING):
    """Mapping rules: dicts with kc_crop, kc_variant, stage_crop, stage_variants, basis."""
    return _read_csv(path)


def stage_options(kc_crop, stages, mapping):
    """Table 11 options for a Table 12 crop (crop_table.CropKc).

    A rule with an empty kc_variant applies to all variants of the crop. An
    empty stage_variants takes every row of the Table 11 crop; otherwise it is
    a ';'-separated list where "(none)" means rows without a variant.
    """
    out = []
    for rule in mapping:
        if rule["kc_crop"] != kc_crop.crop:
            continue
        v = rule["kc_variant"]
        # Variants added by range splitting extend the printed one ("with frozen soils, hand harvested")
        if v and not (kc_crop.variant == v or kc_crop.variant.startswith(v + ", ")):
            continue
        wanted = [v.strip() for v in rule["stage_variants"].split(";") if v.strip()]
        for s in stages:
            if s.crop != rule["stage_crop"]:
                continue
            if wanted and (s.variant or NO_VARIANT) not in wanted:
                continue
            if s not in out:
                out.append(s)
    return out


def season_kc_series(kc_crop, stage, planting_date):
    """Daily (date, kc, stage name) for a CropKc grown with a StageLengths option."""
    return water_balance.kc_series(planting_date, kc_crop.kc_ini, kc_crop.kc_mid,
                                   kc_crop.kc_end, *stage.lengths)


def load_user_stage_csv(path):
    """User stage lengths with columns crop, variant (optional), l_ini, l_dev, l_mid, l_late,
    plant_date and region (optional)."""
    out = []
    for i, row in enumerate(_read_csv(path), start=2):
        try:
            lengths = [int(row[c]) for c in STAGE_COLUMNS]
        except (KeyError, TypeError, ValueError):
            raise ValueError("{}: line {} needs whole-day l_ini, l_dev, l_mid, l_late".format(path, i))
        if min(lengths) < 0 or sum(lengths) == 0:
            raise ValueError("{}: line {} has invalid stage lengths".format(path, i))
        out.append(StageLengths(row["crop"], row.get("variant", ""), i - 1, *lengths,
                                total_printed=None, plant_date=row.get("plant_date", ""),
                                region=row.get("region", ""),
                                source="user table: " + os.path.basename(path)))
    return out
