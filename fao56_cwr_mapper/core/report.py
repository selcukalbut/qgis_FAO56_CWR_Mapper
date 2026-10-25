"""Run report: method, data source, inputs, results and warnings.

Written for reproducibility: anyone reading the report should be able to
repeat the calculation. Produces plain text or a self-contained HTML page.
"""

import configparser
import html
import os
from datetime import datetime

from ..climate_sources.nasa_power import ATTRIBUTION

REFERENCES = [
    "Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998). Crop evapotranspiration - "
    "Guidelines for computing crop water requirements. FAO Irrigation and Drainage Paper 56. Rome: FAO.",
    "NASA POWER Project, Daily API (https://power.larc.nasa.gov). " + ATTRIBUTION,
]

LIMITATIONS = [
    "Climate data come from NASA POWER, a global grid of roughly 0.5 degrees. Near coasts and in "
    "complex terrain it can differ markedly from local conditions; compare with station data.",
    "No soil water storage is modelled: rainfall can only offset demand within the same period "
    "(dekad or day). Requirements of crops grown in the rainy season (e.g. winter cereals) are "
    "therefore overestimated. A soil water balance is planned for a later version.",
    "Kc values are the FAO-56 Table 12 values for a sub-humid climate (RHmin about 45 %, u2 about "
    "2 m/s); the climatic adjustment of Kc mid and Kc end (FAO-56 Eq. 62 and 65) is not applied.",
    "FAO-56 Table 11 stage lengths are examples for specific regions and planting dates; local "
    "stage lengths give more reliable results.",
]


def plugin_version():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metadata.txt")
    cfg = configparser.ConfigParser()
    try:
        cfg.read(path, encoding="utf-8")
        return cfg.get("general", "version")
    except (configparser.Error, OSError):
        return "unknown"


def method_lines(settings):
    nir = ("per dekad (10-day periods, as in CROPWAT): NIR = max(0, sum ETc - sum Pe) for each dekad"
           if settings["nir_period"] == "dekad" else
           "per day: NIR = max(0, ETc - Pe) for each day")
    lines = [
        "Reference evapotranspiration ETo: FAO-56 Penman-Monteith, daily step (Eq. 6), soil heat flux "
        "G = 0. Actual vapour pressure from dewpoint (Eq. 14), from mean relative humidity (Eq. 19) "
        "when dewpoint is missing. Net radiation from measured solar radiation with Rso from Eq. 37 "
        "and albedo 0.23. Wind speed at 2 m as provided by NASA POWER (WS2M).",
        "Elevation for atmospheric pressure and Rso: elevation of the NASA POWER grid cell.",
        "Crop evapotranspiration ETc = Kc x ETo (single crop coefficient). Daily Kc from Kc ini, "
        "Kc mid, Kc end with linear change in the development and late season stages (Eq. 66).",
        "Kc values: FAO-56 Table 12, checked against the printed publication. Ranges explained by a "
        "footnote are separate crop variants; other ranges use their midpoint.",
        "Stage lengths: from stage length fields when given, otherwise an FAO-56 Table 11 example "
        "chosen by region keyword, then by planting month.",
        "Effective rainfall Pe = {:.2f} x P (fixed fraction).".format(settings["pe_fraction"]),
        "Net irrigation requirement " + nir + ". Periods with missing climate data get no value; "
        "missing days are never filled.",
        "Volumes from ellipsoidal field area: 1 mm = 1 m3/da = 10 m3/ha.",
    ]
    if settings.get("efficiency"):
        lines.append("Gross irrigation requirement GIR = NIR / {:.2f} (application efficiency)."
                     .format(settings["efficiency"]))
    return lines


def _fmt(v, nd=1):
    if v is None:
        return "-"
    if isinstance(v, float):
        return "{:,.{}f}".format(v, nd).replace(",", " ")
    return str(v)


RESULT_COLUMNS = [("feature", "Field"), ("crop", "Crop"), ("season", "Season"),
                  ("ETo", "ETo mm"), ("ETc", "ETc mm"), ("P", "P mm"), ("Pe", "Pe mm"),
                  ("NIR", "NIR mm"), ("NIR_m3", "NIR m3"), ("status", "Status")]


def _result_cells(r):
    season = "{} - {}".format(r["season_start"], r["season_end"]) if r.get("season_start") else "-"
    return [r["feature"], r.get("crop") or "-", season] + \
        [_fmt(r.get(k)) for k in ("ETo", "ETc", "P", "Pe", "NIR")] + \
        [_fmt(r.get("NIR_m3"), 0), "ok" if r["status"] == "ok" else r["status"].split(":")[0]]


def totals(results):
    ok = [r for r in results if r.get("NIR") is not None]
    with_area = [r for r in ok if r.get("area_m2")]
    area = sum(r["area_m2"] for r in with_area)
    volume = sum(r["NIR_m3"] for r in with_area)
    return {"features": len(results), "computed": len(ok),
            "failed": sum(1 for r in results if r["status"].startswith("error")),
            "warnings": sum(1 for r in results if r["status"].startswith("warning")),
            "area_ha": area / 10000.0 if with_area else None,
            "volume_m3": volume if with_area else None,
            "mean_nir_mm": volume / area * 1000.0 if area else None}


def _sections(meta, settings, results):
    t = totals(results)
    starts = [r["season_start"] for r in results if r.get("season_start")]
    ends = [r["season_end"] for r in results if r.get("season_end")]
    inputs = [
        ("Input layer", meta.get("layer", "-")),
        ("Features", "{} ({} computed, {} with warnings, {} failed)".format(
            t["features"], t["computed"], t["warnings"], t["failed"])),
        ("CRS / ellipsoid", "{} / {}".format(meta.get("crs", "-"), meta.get("ellipsoid", "-"))),
        ("Crop", settings.get("crop_source", "-")),
        ("Planting date", settings.get("planting_source", "-")),
        ("Stage lengths", settings.get("stage_source", "-")),
        ("Effective rainfall fraction", "{:.2f}".format(settings["pe_fraction"])),
        ("Net irrigation evaluated per", settings["nir_period"]),
        ("Application efficiency", "{:.2f}".format(settings["efficiency"]) if settings.get("efficiency") else "not used"),
        ("User Kc table", settings.get("user_kc_csv") or "none"),
    ]
    data = [
        ("Source", "NASA POWER daily point API, community AG"),
        ("Seasons covered", "{} to {}".format(min(starts), max(ends)) if starts else "-"),
        ("Run date", meta.get("run_time", "-")),
        ("Attribution", ATTRIBUTION),
    ]
    summary = [
        ("Total area", "{} ha".format(_fmt(t["area_ha"], 2)) if t["area_ha"] else "-"),
        ("Total net irrigation volume", "{} m3".format(_fmt(t["volume_m3"], 0)) if t["volume_m3"] else "-"),
        ("Area-weighted net irrigation", "{} mm".format(_fmt(t["mean_nir_mm"])) if t["mean_nir_mm"] else "-"),
    ]
    warnings = [(r["feature"], r["status"]) for r in results if r["status"] != "ok"]
    return inputs, data, summary, warnings


def build_text(meta, settings, results):
    inputs, data, summary, warnings = _sections(meta, settings, results)
    out = ["FAO-56 Crop Water Requirement Mapper - run report", "=" * 50, "",
           "Generated: {}   Plugin version: {}   QGIS: {}".format(
               meta.get("run_time", "-"), meta.get("plugin_version", "-"), meta.get("qgis_version", "-")), ""]

    def kv(title, rows):
        out.extend([title, "-" * len(title)])
        width = max(len(k) for k, _ in rows)
        out.extend("{:<{w}}  {}".format(k, v, w=width) for k, v in rows)
        out.append("")

    kv("Inputs", inputs)
    out.extend(["Method", "------"] + ["- " + line for line in method_lines(settings)] + [""])
    kv("Climate data", data)
    kv("Summary", summary)
    rows = [[h for _, h in RESULT_COLUMNS]] + [_result_cells(r) for r in results]
    widths = [max(len(str(row[i])) for row in rows) for i in range(len(RESULT_COLUMNS))]
    out.extend(["Results per field", "-----------------"])
    for row in rows:
        out.append("  ".join(str(c).ljust(w) for c, w in zip(row, widths)).rstrip())
    out.append("")
    out.extend(["Warnings and errors", "-------------------"])
    out.extend(["- {}: {}".format(f, s) for f, s in warnings] or ["none"])
    out.append("")
    out.extend(["Limitations", "-----------"] + ["- " + x for x in LIMITATIONS] + [""])
    out.extend(["References", "----------"] + ["- " + x for x in REFERENCES])
    return "\n".join(out) + "\n"


CSS = """body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;margin:24px;color:#1f2933;
max-width:1100px}h1{font-size:20px;margin-bottom:4px}h2{font-size:15px;margin-top:22px;
border-bottom:1px solid #d9dee3;padding-bottom:3px}table{border-collapse:collapse;font-size:13px}
td,th{padding:3px 8px;border-bottom:1px solid #eceff1;text-align:left;vertical-align:top}
th{background:#f3f5f7}td.n{text-align:right;font-variant-numeric:tabular-nums}.meta{color:#5f6b76;
font-size:12px}li{margin:3px 0;font-size:13px}.warn{color:#8a5a00}.err{color:#b42318}"""


def build_html(meta, settings, results):
    def e(text):  # element text only; quotes need no escaping there
        return html.escape(text, quote=False)

    inputs, data, summary, warnings = _sections(meta, settings, results)

    def kv(rows):
        return "<table>" + "".join("<tr><th>{}</th><td>{}</td></tr>".format(e(k), e(str(v)))
                                   for k, v in rows) + "</table>"

    numeric = {"ETo mm", "ETc mm", "P mm", "Pe mm", "NIR mm", "NIR m3"}
    head = "".join("<th>{}</th>".format(e(h)) for _, h in RESULT_COLUMNS)
    body = ""
    for r in results:
        cells = _result_cells(r)
        body += "<tr>" + "".join(
            '<td class="n">{}</td>'.format(e(str(c))) if h in numeric else "<td>{}</td>".format(e(str(c)))
            for c, (_, h) in zip(cells, RESULT_COLUMNS)) + "</tr>"
    warn = "".join('<li class="{}"><b>{}</b>: {}</li>'.format(
        "err" if s.startswith("error") else "warn", e(str(f)), e(s)) for f, s in warnings) or "<li>none</li>"
    return """<!doctype html><html><head><meta charset="utf-8">
<title>FAO-56 crop water requirement report</title><style>{css}</style></head><body>
<h1>FAO-56 Crop Water Requirement Mapper &ndash; run report</h1>
<p class="meta">Generated {time} &middot; plugin {ver} &middot; QGIS {qgis}</p>
<h2>Inputs</h2>{inputs}
<h2>Method</h2><ul>{method}</ul>
<h2>Climate data</h2>{data}
<h2>Summary</h2>{summary}
<h2>Results per field</h2><table><tr>{head}</tr>{body}</table>
<h2>Warnings and errors</h2><ul>{warn}</ul>
<h2>Limitations</h2><ul>{lim}</ul>
<h2>References</h2><ul>{refs}</ul>
</body></html>
""".format(css=CSS, time=e(meta.get("run_time", "-")), ver=e(meta.get("plugin_version", "-")),
           qgis=e(meta.get("qgis_version", "-")), inputs=kv(inputs),
           method="".join("<li>{}</li>".format(e(x)) for x in method_lines(settings)),
           data=kv(data), summary=kv(summary), head=head, body=body, warn=warn,
           lim="".join("<li>{}</li>".format(e(x)) for x in LIMITATIONS),
           refs="".join("<li>{}</li>".format(e(x)) for x in REFERENCES))


def write_report(path, meta, settings, results):
    """Write HTML for .html/.htm paths, plain text otherwise."""
    meta = dict(meta)
    meta.setdefault("run_time", datetime.now().strftime("%Y-%m-%d %H:%M"))
    meta.setdefault("plugin_version", plugin_version())
    as_html = path.lower().endswith((".html", ".htm"))
    content = build_html(meta, settings, results) if as_html else build_text(meta, settings, results)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path
