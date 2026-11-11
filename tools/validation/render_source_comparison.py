"""Markdown tables from tools/validation/local/source_comparison.json (plain Python).

    python3 tools/validation/render_source_comparison.py            # NASA POWER and Open-Meteo only
    python3 tools/validation/render_source_comparison.py --station  # with the GSOD station (local use only)
"""

import argparse
import json
import os

LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local")
GRID = ["NASA POWER", "Open-Meteo ERA5-Seamless"]
STATION = "Station 17056 (GSOD)"
PE = ["Fixed 0.8", "USDA SCS (CROPWAT)", "USDA SCS (NEH 623, D = 75 mm)"]
SHORT = {"NASA POWER": "POWER", "Open-Meteo ERA5-Seamless": "Open-Meteo", STATION: "İstasyon"}
CROPS = {"Field A": "Mısır", "Field B": "Ayçiçeği", "Field C": "Domates", "Field D": "Kışlık buğday"}


def fmt(v, nd=0):
    return "–" if v is None else "{:.{}f}".format(v, nd).replace(".", ",")


def season_table(d, sources):
    base = d["results"]
    lines = ["| Parsel | Sezon | " + " | ".join("ETo {}".format(SHORT[s]) for s in sources)
             + " | " + " | ".join("P {}".format(SHORT[s]) for s in sources) + " |",
             "|---|---|" + "---:|" * (2 * len(sources))]
    for f in sorted(CROPS):
        r0 = base["{}|{}".format(sources[0], PE[0])][f]
        lines.append("| {} ({}) | {} – {} | ".format(f, CROPS[f], r0["season_beg"], r0["season_end"])
                     + " | ".join(fmt(base["{}|{}".format(s, PE[0])][f]["ETo_mm"]) for s in sources) + " | "
                     + " | ".join(fmt(base["{}|{}".format(s, PE[0])][f]["P_mm"]) for s in sources) + " |")
    return "\n".join(lines)


def nir_table(d, sources):
    base = d["results"]
    head = ["| Parsel | Pe yöntemi | " + " | ".join("Pe {}".format(SHORT[s]) for s in sources) + " | "
            + " | ".join("NIR {}".format(SHORT[s]) for s in sources) + " |",
            "|---|---|" + "---:|" * (2 * len(sources))]
    for f in sorted(CROPS):
        for pe in PE:
            head.append("| {} | {} | ".format(f if pe == PE[0] else "", pe)
                        + " | ".join(fmt(base["{}|{}".format(s, pe)][f]["Pe_mm"]) for s in sources) + " | "
                        + " | ".join(fmt(base["{}|{}".format(s, pe)][f]["NIR_mm"]) for s in sources) + " |")
    return "\n".join(head)


def monthly_table(d, sources):
    months = sorted({k.split("|")[1] for k in d["monthly"]})
    cols = [("tmax", "Tmax °C", 1), ("tmin", "Tmin °C", 1), ("tdew", "Td °C", 1), ("u2", "u2 m/s", 1),
            ("rs", "Rs MJ/m²/gün", 1), ("ETo", "ETo mm", 0), ("P", "P mm", 0)]
    lines = ["| Ay | Kaynak | " + " | ".join(c[1] for c in cols) + " |", "|---|---|" + "---:|" * len(cols)]
    for m in months:
        for s in sources:
            v = d["monthly"]["{}|{}".format(s, m)]
            lines.append("| {} | {} | ".format(m if s == sources[0] else "", SHORT[s])
                         + " | ".join(fmt(v[k], nd) for k, _, nd in cols) + " |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--station", action="store_true")
    ap.add_argument("--json", default=os.path.join(LOCAL, "source_comparison.json"))
    args = ap.parse_args()
    with open(args.json, encoding="utf-8") as fh:
        d = json.load(fh)
    sources = GRID + ([STATION] if args.station else [])
    print("### Sezon toplamları (mm)\n\n" + season_table(d, sources))
    print("\n### Etkili yağış ve net sulama (mm)\n\n" + nir_table(d, sources))
    print("\n### Aylık girdiler, Parsel C noktası\n\n" + monthly_table(d, sources))
    print("\nYükseklik (m): " + ", ".join("{} {}".format(SHORT[s], fmt(d["elevation"][s], 0)) for s in sources))


if __name__ == "__main__":
    main()
