"""Run report: method, data source, inputs, results and warnings.

Written for reproducibility: anyone reading the report should be able to
repeat the calculation. Produces plain text or a self-contained HTML page.
"""

import configparser
import html
import os
from datetime import datetime

from ..climate_sources import open_meteo
from ..climate_sources.nasa_power import ATTRIBUTION

FAO56_REFERENCE = (
    "Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998). Crop evapotranspiration - "
    "Guidelines for computing crop water requirements. FAO Irrigation and Drainage Paper 56. Rome: FAO.")
POWER_REFERENCE = "NASA POWER Project, Daily API (https://power.larc.nasa.gov). " + ATTRIBUTION

OPEN_METEO_REFERENCES = (
    "Zippenfenig, P. (2023). Open-Meteo.com Weather API. Zenodo. "
    "https://doi.org/10.5281/ZENODO.7970649",
    "Hersbach, H. et al. (2023). ERA5 hourly data on single levels from 1940 to present. Copernicus "
    "Climate Change Service (C3S) Climate Data Store. https://doi.org/10.24381/cds.adbb2d47",
    "Muñoz Sabater, J. (2019). ERA5-Land hourly data from 1950 to present. Copernicus Climate Change "
    "Service (C3S) Climate Data Store. https://doi.org/10.24381/CDS.E2161BAC",
)
OPEN_METEO_LIMITATION = (
    "Climate data come from the Open-Meteo Historical Weather API (ECMWF ERA5 / ERA5-Land "
    "reanalysis, 0.25 and 0.1 degree grids; temperatures are downscaled to a 90 m elevation model). "
    "Reanalysis smooths local extremes and coastal effects; compare with station data. " + open_meteo.TERMS)

POWER_LIMITATION = (
    "Climate data come from NASA POWER, a global grid (meteorology 0.5 x 0.625 degrees, solar "
    "radiation 1 x 1 degree). Near coasts and in complex terrain it can differ markedly from local "
    "conditions; compare with station data.")
STATION_LIMITATIONS = (
    "Station data are used as given; quality control is limited to range checks (Tmax < Tmin "
    "swapped, relative humidity outside 0-100 % and negative values ignored).",
    )
NEAREST_LIMITATION = "Each field uses its nearest station; climate between stations is not interpolated."
THIESSEN_LIMITATION = (
    "Thiessen weighting assumes that each station represents the area closest to it; relief, "
    "coastline and elevation differences between stations are not taken into account.")
ESTIMATION_LIMITATION = (
    "Estimated inputs (FAO-56 missing-data procedures) are less accurate than measurements; "
    "ea from Tmin (Eq. 48) can overestimate humidity in arid climates.")

COMMON_LIMITATIONS = [
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


def _climate(settings):
    return settings.get("climate") or {"source": "power"}


def references(settings):
    source = _climate(settings)["source"]
    refs = [FAO56_REFERENCE]
    refs += {"usda_cropwat": [CROPWAT_REFERENCE], "usda_neh": [USDA_NEH_REFERENCE]}.get(
        _pe_method(settings), [])
    if source == "power":
        refs.append(POWER_REFERENCE)
    elif source == "open_meteo":
        refs += list(OPEN_METEO_REFERENCES)
    return refs


def limitations(settings):
    out = _climate_limitations(settings)
    return out + ([SCS_LIMITATION] if _pe_method(settings) != "fixed" else [])


def _climate_limitations(settings):
    c = _climate(settings)
    if c["source"] == "power":
        return [POWER_LIMITATION] + COMMON_LIMITATIONS
    if c["source"] == "open_meteo":
        return [OPEN_METEO_LIMITATION] + COMMON_LIMITATIONS
    extra = [THIESSEN_LIMITATION if c.get("assignment") == "thiessen" else NEAREST_LIMITATION]
    extra += [ESTIMATION_LIMITATION] if c.get("estimation") else []
    return list(STATION_LIMITATIONS) + extra + COMMON_LIMITATIONS


def _assignment_line(c):
    km = "{:g}".format(float(c.get("max_distance_km", 0)))
    if c.get("assignment") == "thiessen":
        return ("Polygons are weighted by the ellipsoidal area of their intersection with the Thiessen "
                "polygons of the stations (stations farther than {} km from the field are left out); each "
                "station's daily ETo uses the field's latitude and the station elevation, and the field's "
                "daily ETo and rainfall are the area-weighted means. On days without data at a station the "
                "other weights are rescaled to 1. Points use the nearest station.".format(km))
    return ("Each field uses the nearest station within {} km; elevation for atmospheric pressure and "
            "Rso is the station elevation.".format(km))


def _climate_method_lines(settings):
    c = _climate(settings)
    if c["source"] == "power":
        return [
            "Reference evapotranspiration ETo: FAO-56 Penman-Monteith, daily step (Eq. 6), soil heat "
            "flux G = 0. Actual vapour pressure from dewpoint (Eq. 14), from mean relative humidity "
            "(Eq. 19) when dewpoint is missing. Net radiation from measured solar radiation with Rso "
            "from Eq. 37 and albedo 0.23. Wind speed at 2 m as provided by NASA POWER (WS2M), at least "
            "0.5 m/s.",
            "Elevation for atmospheric pressure and Rso: elevation of the NASA POWER grid cell.",
        ]
    if c["source"] == "open_meteo":
        return [
            "Reference evapotranspiration ETo: FAO-56 Penman-Monteith, daily step (Eq. 6), soil heat "
            "flux G = 0, computed by the plugin from Open-Meteo daily values (model {}): Tmax, Tmin, "
            "mean dewpoint (ea from Eq. 14; mean RH, Eq. 19, when dewpoint is missing), shortwave "
            "radiation sum with Rso from Eq. 37 and albedo 0.23, and mean 10 m wind speed converted to "
            "2 m (Eq. 47), at least 0.5 m/s. Open-Meteo's own FAO ET0 is not used.".format(
                open_meteo.MODEL_NAMES.get(c.get("model"), c.get("model", "-"))),
            "Elevation for atmospheric pressure and Rso: point elevation returned by Open-Meteo (90 m "
            "elevation model). Fields within about 1 km (0.01 degree) share one download.",
        ]
    lines = [
        "Reference evapotranspiration ETo: FAO-56 Penman-Monteith, daily step (Eq. 6), soil heat flux "
        "G = 0, from weather station data. Actual vapour pressure from dewpoint (Eq. 14), RHmax and "
        "RHmin (Eq. 17), RHmax (Eq. 18) or mean RH (Eq. 19), in this order. Solar radiation as "
        "measured or from sunshine duration (Angstrom, Eq. 35, as = 0.25, bs = 0.50); Rso from Eq. 37, "
        "albedo 0.23. Wind speed converted from {} m to 2 m (Eq. 47), at least 0.5 m/s.".format(
            "{:g}".format(float(c.get("wind_height", 2.0)))),
        _assignment_line(c)]
    if c.get("estimation"):
        lines.append(
            "Missing inputs are estimated with the FAO-56 procedures for missing climatic data: ea from "
            "Tmin (Eq. 48), Rs = kRs sqrt(Tmax - Tmin) Ra (Hargreaves, Eq. 50, kRs = {:.2f}) and "
            "u2 = 2 m/s. Estimated variables and days are listed under warnings.".format(c.get("krs", 0.16)))
    else:
        lines.append("Days with missing humidity, radiation or wind data are not computed.")
    return lines


USDA_NEH_REFERENCE = (
    "USDA NRCS (1993). National Engineering Handbook, Part 623 Irrigation, Chapter 2: Irrigation "
    "Water Requirements (210-vi-NEH), section 623.0207 Effective precipitation. Washington, DC.")
CROPWAT_REFERENCE = (
    "Smith, M. (1992). CROPWAT - A computer program for irrigation planning and management. "
    "FAO Irrigation and Drainage Paper 46. Rome: FAO.")
SCS_LIMITATION = (
    "The USDA SCS effective rainfall formulas were derived for monthly totals (50 years of records "
    "at 22 US locations); applied per dekad scaled to a month they are an approximation. They do not "
    "consider infiltration rate, rainfall intensity or slope and overestimate Pe on poorly drained "
    "soils (NEH 623).")


def _pe_method(settings):
    return settings.get("pe_method", "fixed")


def _pe_input(settings):
    m = _pe_method(settings)
    if m == "usda_cropwat":
        return "USDA SCS, CROPWAT form"
    if m == "usda_neh":
        return "USDA SCS, NEH Part 623 (usable soil water storage D = {:g} mm)".format(
            settings.get("pe_storage_mm", 75.0))
    return "fixed fraction {:.2f}".format(settings["pe_fraction"])


def _pe_line(settings):
    m = _pe_method(settings)
    scaled = (" The formula is monthly: each dekad's totals are scaled to a month (x days in "
              "the month / days in the dekad), the formula applied and the result scaled back (factor 3 "
              "for a 10-day dekad of a 30-day month); the dekad Pe is shared among its days in "
              "proportion to rainfall. Days with missing data are left out.")
    if m == "usda_cropwat":
        return ("Effective rainfall: USDA Soil Conservation Service method as in CROPWAT (Smith 1992): "
                "Pe = P (125 - 0.2 P) / 125 for P <= 250 mm, Pe = 125 + 0.1 P for P > 250 mm "
                "(monthly totals)." + scaled)
    if m == "usda_neh":
        return ("Effective rainfall: USDA SCS method, NEH Part 623 Eq. 2-84: Pe = SF (0.70917 P^0.82416 "
                "- 0.11556) 10^(0.02426 ETc) in inches, with the soil water storage factor of Eq. 2-85, "
                "SF = 0.531747 + 0.295164 D - 0.057697 D^2 + 0.003804 D^3 (D = {:g} mm = {:.2f} in); Pe "
                "is limited to the lesser of P and ETc.".format(
                    settings.get("pe_storage_mm", 75.0), settings.get("pe_storage_mm", 75.0) / 25.4) + scaled)
    return "Effective rainfall Pe = {:.2f} x P (fixed fraction).".format(settings["pe_fraction"])


def method_lines(settings):
    nir = ("per dekad (10-day periods, as in CROPWAT): NIR = max(0, sum ETc - sum Pe) for each dekad"
           if settings["nir_period"] == "dekad" else
           "per day: NIR = max(0, ETc - Pe) for each day")
    lines = _climate_method_lines(settings) + [
        "Crop evapotranspiration ETc = Kc x ETo (single crop coefficient). Daily Kc from Kc ini, "
        "Kc mid, Kc end with linear change in the development and late season stages (Eq. 66).",
        "Kc values: FAO-56 Table 12, checked against the printed publication. Ranges explained by a "
        "footnote are separate crop variants; other ranges use their midpoint.",
        "Stage lengths: from stage length fields when given, otherwise an FAO-56 Table 11 example "
        "chosen by region keyword, then by planting month.",
        _pe_line(settings),
        "Net irrigation requirement " + nir + ". Periods with missing climate data get no value; "
        "missing days are never filled{}.".format(
            "" if _climate(settings)["source"] in ("power", "open_meteo") else " (only individual inputs are estimated)"
            if _climate(settings).get("estimation") else ""),
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


NEAR_REAL_TIME = ("GEOSIT", "FLASHFLUX")

RESULT_COLUMNS = [("feature", "Field"), ("crop", "Crop"), ("season", "Season"),
                  ("stage", "Stage lengths (ini/dev/mid/late)"), ("climate", "Climate data"),
                  ("ETo", "ETo mm"), ("ETc", "ETc mm"), ("P", "P mm"), ("Pe", "Pe mm"),
                  ("NIR", "NIR mm"), ("NIR_m3", "NIR m3"), ("status", "Status")]


def _result_cells(r):
    season = "{} - {}".format(r["season_start"], r["season_end"]) if r.get("season_start") else "-"
    stage = "-"
    if r.get("stage_lengths"):
        stage = "{} d".format("/".join(str(x) for x in r["stage_lengths"]))
        if r.get("stage_example"):
            stage = "{}: {}".format(r["stage_example"], stage)
    return [r["feature"], r.get("crop") or "-", season, stage, r.get("climate") or "-"] + \
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
        ("Effective rainfall", _pe_input(settings)),
        ("Net irrigation evaluated per", settings["nir_period"]),
        ("Application efficiency", "{:.2f}".format(settings["efficiency"]) if settings.get("efficiency") else "not used"),
        ("User Kc table", settings.get("user_kc_csv") or "none"),
    ]
    products = sorted({p for r in results for p in r.get("climate_sources") or []})
    versions = sorted({r["api_version"] for r in results if r.get("api_version")})
    c = _climate(settings)
    if c["source"] == "open_meteo":
        data = [
            ("Source", "Open-Meteo Historical Weather API (archive-api.open-meteo.com)"),
            ("Model", open_meteo.MODEL_NAMES.get(c.get("model"), c.get("model", "-"))),
            ("Downloads", str(c["downloads"]) if c.get("downloads") is not None else "-"),
            ("Seasons covered", "{} to {}".format(min(starts), max(ends)) if starts else "-"),
            ("Run date", meta.get("run_time", "-")),
            ("Terms", open_meteo.TERMS),
            ("Attribution", open_meteo.ATTRIBUTION),
        ]
        return inputs, data, _summary(t), _warning_rows(results)
    if c["source"] != "power":
        data = [
            ("Source", "Weather station data (CSV)"),
            ("File", c.get("file", "-")),
            ("Stations used", ", ".join(p.replace("station ", "") for p in products) or "-"),
            ("Assignment", ("Thiessen area weighting of daily ETo and rainfall, stations within {} km"
                            if c.get("assignment") == "thiessen" else "nearest station within {} km").format(
                "{:g}".format(float(c.get("max_distance_km", 0))))),
            ("Wind measurement height", "{} m".format("{:g}".format(float(c.get("wind_height", 2.0))))),
            ("Missing inputs", "estimated (FAO-56 Eq. 48, Eq. 50 with kRs = {:.2f}, u2 = 2 m/s)".format(
                c.get("krs", 0.16)) if c.get("estimation") else "not estimated"),
            ("Seasons covered", "{} to {}".format(min(starts), max(ends)) if starts else "-"),
            ("Run date", meta.get("run_time", "-")),
        ]
        return inputs, data, _summary(t), _warning_rows(results)
    data = [
        ("Source", "NASA POWER daily point API, community AG"),
        ("API version", ", ".join(versions) or "-"),
        ("POWER data products", ", ".join(products) or "-"),
        ("Seasons covered", "{} to {}".format(min(starts), max(ends)) if starts else "-"),
        ("Run date", meta.get("run_time", "-")),
        ("Attribution", ATTRIBUTION),
    ]
    if any(p in NEAR_REAL_TIME for p in products):
        data.insert(4, ("Note", "Near-real-time products ({}) were used for recent days; POWER "
                                "replaces them later, so repeating the run can give slightly "
                                "different values.".format(", ".join(p for p in products
                                                                     if p in NEAR_REAL_TIME))))
    return inputs, data, _summary(t), _warning_rows(results)


def _summary(t):
    return [
        ("Total area (fields with a net irrigation value)",
         "{} ha".format(_fmt(t["area_ha"], 2)) if t["area_ha"] else "-"),
        ("Total net irrigation volume", "{} m3".format(_fmt(t["volume_m3"], 0)) if t["volume_m3"] else "-"),
        ("Area-weighted net irrigation", "{} mm".format(_fmt(t["mean_nir_mm"])) if t["mean_nir_mm"] else "-"),
    ]


def _warning_rows(results):
    return [(r["feature"], r["status"]) for r in results if r["status"] != "ok"]


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
    out.extend(["Limitations", "-----------"] + ["- " + x for x in limitations(settings)] + [""])
    out.extend(["References", "----------"] + ["- " + x for x in references(settings)])
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
           lim="".join("<li>{}</li>".format(e(x)) for x in limitations(settings)),
           refs="".join("<li>{}</li>".format(e(x)) for x in references(settings)))


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
