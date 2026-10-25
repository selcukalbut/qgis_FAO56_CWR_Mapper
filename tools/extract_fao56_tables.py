"""Extract FAO-56 Table 11 (stage lengths) and Table 12 (Kc) into CSV files.

Source: Chapter 6 of FAO-56 as published at https://www.fao.org/3/x0490e/x0490e0b.htm
Save that page locally and run from the repository root:

    python3 -I tools/extract_fao56_tables.py x0490e0b.htm

Values are copied as text exactly as printed (ranges "0.70-0.90" and
alternatives "50/30" are kept). Footnote markers are moved to a separate
column. Every row is then checked automatically (stage sum = total, numeric
ranges); rows that fail are listed as REVIEW items to be compared with the
printed book. Confirmed fixes go to tools/fao56_corrections.csv, never into
the extracted values directly, so every deviation from the HTML is documented.
"""

import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fao56_html_tables import table_rows  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "fao56_cwr_mapper", "data")
CORRECTIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fao56_corrections.csv")

FOOTNOTE = re.compile(r"\s*\[\^([^\]]*)\]")
GROUP = re.compile(r"^([a-p])\. (.+)$")
NUM = r"\d+(?:\.\d+)?"
VALUE = re.compile(r"^{0}(?:\s*[-/]\s*{0})?$".format(NUM))


def split_footnotes(text):
    notes = [n.strip() for n in FOOTNOTE.findall(text) if n.strip() not in ("st", "nd")]
    clean = FOOTNOTE.sub(lambda m: m.group(1) if m.group(1) in ("st", "nd") else "", text)
    return clean.strip(), notes


def numbers(text):
    return [float(x) for x in re.findall(NUM, text)]


def load_corrections():
    """{(table, crop, variant_or_row, column): (value, reason)}"""
    out = {}
    if os.path.exists(CORRECTIONS):
        with open(CORRECTIONS, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                out[(r["table"], r["crop"], r["key"], r["column"])] = (r["value"], r["reason"])
    return out


def extract_table12(rows, corrections, review):
    out, group, group_vals, crop = [], "", ("", "", ""), ""
    for cells in rows[1:]:
        cells = (cells + [""] * 6)[:6]
        name, notes = split_footnotes(cells[0])
        variant = cells[1].lstrip("- ").strip()
        vals = [split_footnotes(c) for c in cells[2:6]]
        notes += [n for _, ns in vals for n in ns]
        kc_ini, kc_mid, kc_end, height = (v for v, _ in vals)
        m = GROUP.match(name)
        if m:
            group = name
            group_vals = (kc_ini, kc_mid, kc_end)
            continue
        if name:
            crop = name
        if not (kc_mid or kc_end):          # crop header row with variants below
            continue
        row = {"group": group, "crop": crop, "variant": variant,
               "kc_ini": kc_ini, "kc_mid": kc_mid, "kc_end": kc_end,
               "kc_ini_from_group": "", "max_height_m": height,
               "footnotes": " ".join(notes), "correction": ""}
        if not row["kc_ini"]:
            row["kc_ini"], row["kc_ini_from_group"] = group_vals[0], "yes"
        for col in ("kc_ini", "kc_mid", "kc_end"):
            key = ("12", crop, variant, col)
            if key in corrections:
                row[col], reason = corrections[key]
                row["correction"] = (row["correction"] + "; " if row["correction"] else "") + reason
        label = crop + (" / " + variant if variant else "")
        for col in ("kc_ini", "kc_mid", "kc_end"):
            v = row[col]
            if not v:
                review.append(("12", label, col, "empty"))
            elif not VALUE.match(v):
                review.append(("12", label, col, "not a number: " + v))
            elif re.search(r"\.\d{3,}", v):
                review.append(("12", label, col, "more than 2 decimals (footnote stuck?): " + v))
            elif any(x < 0.1 or x > 1.4 for x in numbers(v)):
                review.append(("12", label, col, "outside 0.1-1.4: " + v))
            elif "-" in v:
                review.append(("12", label, col, "range, needs a rule: " + v))
        out.append(row)
    return out


def extract_table11(rows, corrections, review):
    out, group, crop, variant, n = [], "", "", "", 0
    for cells in rows[1:]:
        first, _ = split_footnotes(cells[0])
        if GROUP.match(first):
            group = first
            continue
        if re.match(r"^\d", first):       # continuation row (rowspan) of last crop
            stages = cells[0:5]
            plant, region = (cells + ["", ""])[5:7]
        else:
            if first and first[0].islower():   # e.g. "year 2" under "Cassava: year 1"
                crop, n = crop.split(":")[0] + ": " + first, 0
            elif first:
                crop, n = first, 0
            variant = cells[1].lstrip("- ").strip()
            stages = cells[2:7]
            plant, region = (cells + ["", "", "", ""])[7:9]
        n += 1
        clean = [split_footnotes(c) for c in stages]
        notes = [x for _, ns in clean for x in ns]
        l_ini, l_dev, l_mid, l_late, total = (v for v, _ in clean)
        row = {"group": group, "crop": crop, "variant": variant, "row": n,
               "l_ini": l_ini, "l_dev": l_dev, "l_mid": l_mid, "l_late": l_late,
               "total": total, "plant_date": plant, "region": region,
               "footnotes": " ".join(notes), "correction": ""}
        row_key = "{}{}".format(variant + " " if variant else "", n)
        for col in ("l_ini", "l_dev", "l_mid", "l_late", "total", "remark"):
            key = ("11", crop, row_key, col)
            if key in corrections:
                value, reason = corrections[key]
                if col != "remark":          # "remark" documents a row without changing values
                    row[col] = value
                row["correction"] = (row["correction"] + "; " if row["correction"] else "") + reason
        remark = ("11", crop, row_key, "remark") in corrections
        label = "{}{} (row {}, {} {})".format(crop, " / " + variant if variant else "", n, plant, region).strip()
        parts = [row[c] for c in ("l_ini", "l_dev", "l_mid", "l_late")]
        if not all(re.match(r"^\d+(/\d+)?$", p) for p in parts) or not re.match(r"^\d+(/\d+)?$", row["total"]):
            if "var" not in row["l_mid"] and "--" not in row["l_mid"]:
                review.append(("11", label, "stages", "not an integer: " + " | ".join(parts + [row["total"]])))
        elif "/" not in "".join(parts + [row["total"]]):
            s = sum(int(p) for p in parts)
            if s != int(row["total"]) and not remark:
                review.append(("11", label, "total", "stages sum to {} but total is {}".format(s, row["total"])))
        else:
            review.append(("11", label, "stages", "alternative values: " + " | ".join(parts + [row["total"]])))
        out.append(row)
    return out


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main(page):
    with open(page, encoding="latin-1") as fh:
        html_text = fh.read()
    corrections, review = load_corrections(), []
    t12 = extract_table12(table_rows(html_text, "TABLE 12"), corrections, review)
    t11 = extract_table11(table_rows(html_text, "TABLE 11"), corrections, review)
    os.makedirs(OUT_DIR, exist_ok=True)
    write_csv(os.path.join(OUT_DIR, "fao56_table12_kc.csv"), t12)
    write_csv(os.path.join(OUT_DIR, "fao56_table11_stage_lengths.csv"), t11)
    print("Table 12: {} rows, Table 11: {} rows, {} corrections applied".format(
        len(t12), len(t11), len(corrections)))
    print("REVIEW ({} items):".format(len(review)))
    for table, label, col, msg in review:
        print("  T{}  {:<70} {:<8} {}".format(table, label[:70], col, msg))


if __name__ == "__main__":
    main(sys.argv[1])
