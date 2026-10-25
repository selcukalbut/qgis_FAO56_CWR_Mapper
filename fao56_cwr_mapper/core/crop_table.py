"""Crop coefficient (Kc) table built from FAO-56 Table 12.

data/fao56_table12_kc.csv holds the values as printed in FAO-56 (book-checked,
see docs/fao56_table_review.md). This module turns them into usable crops:

- Ranges explained by a footnote (e.g. maize Kc_end 0.60-0.35, footnote 11)
  become separate variants, defined in data/kc_range_variants.csv.
- Other ranges (e.g. tomato Kc_end 0.70-0.90) default to the midpoint; the
  printed range is kept in ``kc_range`` and the user can override the value.
- Group "p. Special" (open water) is not a crop and is left out.
"""

import csv
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
KC_TABLE = os.path.join(DATA_DIR, "fao56_table12_kc.csv")
RANGE_VARIANTS = os.path.join(DATA_DIR, "kc_range_variants.csv")
EXCLUDED_GROUPS = ("p. Special",)
KC_COLUMNS = ("kc_ini", "kc_mid", "kc_end")


class CropKc:
    """Kc values of one crop (or crop variant)."""

    def __init__(self, group, crop, variant, kc_ini, kc_mid, kc_end,
                 max_height_m="", kc_range=None, notes=None, source="FAO-56 Table 12"):
        self.group = group
        self.crop = crop
        self.variant = variant
        self.kc_ini = kc_ini
        self.kc_mid = kc_mid
        self.kc_end = kc_end
        self.max_height_m = max_height_m
        self.kc_range = kc_range or {}   # column -> (low, high) as printed
        self.notes = notes or []
        self.source = source

    @property
    def name(self):
        return "{} - {}".format(self.crop, self.variant) if self.variant else self.crop

    def with_values(self, kc_ini=None, kc_mid=None, kc_end=None):
        """Copy with user-supplied values; overridden columns are noted."""
        new = CropKc(self.group, self.crop, self.variant, self.kc_ini, self.kc_mid,
                     self.kc_end, self.max_height_m, dict(self.kc_range),
                     list(self.notes), self.source)
        for col, value in (("kc_ini", kc_ini), ("kc_mid", kc_mid), ("kc_end", kc_end)):
            if value is not None:
                setattr(new, col, float(value))
                new.notes.append("{} set by user to {}".format(col, value))
        return new

    def __repr__(self):
        return "CropKc({!r}, ini={}, mid={}, end={})".format(
            self.name, self.kc_ini, self.kc_mid, self.kc_end)


def parse_kc(text):
    """'1.05' -> (1.05, None); '0.70-0.90' -> (0.8, (0.7, 0.9))."""
    text = text.strip()
    if "-" in text:
        low, high = (float(x) for x in text.split("-"))
        return (low + high) / 2.0, (low, high)
    return float(text), None


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _join(*parts):
    return ", ".join(p for p in parts if p)


def load_kc_table(path=KC_TABLE, variants_path=RANGE_VARIANTS):
    """List of CropKc, one per crop/variant, in table order."""
    rules = {}
    for r in _read_csv(variants_path):
        rules.setdefault((r["crop"], r["variant"]), []).append(r)

    crops = []
    for row in _read_csv(path):
        if row["group"] in EXCLUDED_GROUPS:
            continue
        notes = [row["correction"]] if row["correction"] else []
        if row["kc_ini_from_group"]:
            notes.append("kc_ini taken from the crop group row")

        split = rules.get((row["crop"], row["variant"]))
        if split:
            for r in split:
                values = {c: parse_kc(row[c])[0] for c in KC_COLUMNS}
                values[r["column"]] = float(r["value"])
                crops.append(CropKc(row["group"], row["crop"], _join(row["variant"], r["new_variant"]),
                                    max_height_m=row["max_height_m"],
                                    notes=notes + ["{} {} ({})".format(r["column"], r["value"], r["basis"])],
                                    **values))
            continue

        values, ranges, crop_notes = {}, {}, list(notes)
        for col in KC_COLUMNS:
            values[col], rng = parse_kc(row[col])
            if rng:
                ranges[col] = rng
                crop_notes.append("{} printed as {}; midpoint {:.3g} used by default".format(
                    col, row[col], values[col]))
        crops.append(CropKc(row["group"], row["crop"], row["variant"],
                            max_height_m=row["max_height_m"], kc_range=ranges,
                            notes=crop_notes, **values))
    return crops


def load_user_kc_csv(path):
    """User crop table with columns crop, variant (optional), kc_ini, kc_mid, kc_end.

    Lets users bring local (e.g. national) coefficients instead of FAO-56 values.
    """
    crops = []
    for i, row in enumerate(_read_csv(path), start=2):
        try:
            values = {c: float(row[c]) for c in KC_COLUMNS}
        except (KeyError, TypeError, ValueError):
            raise ValueError("{}: line {} needs numeric kc_ini, kc_mid, kc_end".format(path, i))
        crops.append(CropKc(row.get("group", ""), row["crop"], row.get("variant", ""),
                            max_height_m=row.get("max_height_m", ""),
                            source="user table: " + os.path.basename(path), **values))
    return crops


def find_crop(crops, name):
    """Crop by its display name (case-insensitive)."""
    key = name.strip().lower()
    for c in crops:
        if c.name.lower() == key:
            return c
    raise KeyError("Crop not found: " + name)
