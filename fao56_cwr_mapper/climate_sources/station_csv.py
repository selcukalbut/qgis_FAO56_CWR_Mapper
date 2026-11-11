"""Daily weather station data from a CSV file (no QGIS dependency).

One file holds one or more stations in long format: one row per station and
day. Columns are recognised by name, in English or Turkish, ignoring case,
spaces, underscores, accents and units in brackets ("Tmax (°C)" = "tmax"):

required  date, tmax, tmin, precip
optional  station (needed when the file holds several stations)
humidity  tdew | rhmax + rhmin | rhmax | rh (daily mean)              [degC, %]
wind      u2 (at 2 m) | wind (at the height given by the caller)    [m/s]
radiation rs (global solar radiation, MJ m-2 day-1) | sunshine (hours)

Delimiters , ; and tab are detected; with ; a decimal comma is accepted.
Dates may be YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY or YYYY/MM/DD. Empty cells,
NA, NaN, -, -999 and -9999 mean "missing". Missing humidity, radiation or wind
can then be estimated with the FAO-56 procedures (core.eto_series.Estimation).
"""

import csv
import io
import re
import unicodedata
from datetime import datetime

from ..core import fao56
from ..core.climate import DailyClimate

ALIASES = {
    "station": ("station", "stationid", "stationno", "id", "istasyon", "istasyonno", "istasyonid",
                "istno", "istasyonadi", "stationname"),
    "date": ("date", "tarih", "day", "gun", "datetime"),
    "tmax": ("tmax", "tmaks", "maxtemp", "maxtemperature", "temperaturemax", "maksimumsicaklik",
             "maxsicaklik", "maksicaklik", "enyuksek", "enyukseksicaklik"),
    "tmin": ("tmin", "mintemp", "mintemperature", "temperaturemin", "minimumsicaklik",
             "minsicaklik", "endusuk", "endusuksicaklik"),
    "tdew": ("tdew", "dewpoint", "dewpointtemperature", "ciynoktasi", "ciynoktasisicakligi"),
    "rh": ("rh", "rhmean", "rhavg", "relativehumidity", "humidity", "nem", "bagilnem",
           "ortalamanem", "ortalamabagilnem"),
    "rhmax": ("rhmax", "maxrh", "maxhumidity", "maksimumnem", "maxnem", "maksnem"),
    "rhmin": ("rhmin", "minrh", "minhumidity", "minimumnem", "minnem"),
    "u2": ("u2", "wind2m", "windspeed2m", "ruzgar2m"),
    "wind": ("wind", "windspeed", "uz", "ruzgar", "ruzgarhizi", "ortalamaruzgarhizi"),
    "rs": ("rs", "radiation", "solarradiation", "globalradiation", "shortwave", "radyasyon",
           "gunesradyasyonu", "globalgunesradyasyonu", "toplamgunesradyasyonu"),
    "sunshine": ("sunshine", "sunshinehours", "sunshineduration", "n", "guneslenme",
                 "guneslenmesuresi", "gunesleme"),
    "precip": ("precip", "precipitation", "rain", "rainfall", "p", "yagis", "toplamyagis",
               "yagismiktari"),
}
REQUIRED = ("date", "tmax", "tmin", "precip")
MISSING = {"", "na", "n/a", "nan", "null", "none", "-", "--", "-999", "-9999", "-99.9", "-999.0", "-9999.0"}
YEAR_FIRST = re.compile(r"^\d{4}([-/.])\d{1,2}\1\d{1,2}$")
DAY_FIRST = re.compile(r"^\d{1,2}([-/.])\d{1,2}\1\d{4}$")
SINGLE_STATION = ""


class StationDataError(Exception):
    """Raised when the CSV cannot be used."""


def normalise(name):
    """'Tmax (°C)' -> 'tmax', 'Güneşlenme Süresi' -> 'guneslenmesuresi'."""
    name = re.split(r"[\(\[]", name, maxsplit=1)[0]
    name = name.replace("ı", "i").replace("İ", "i")
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", name.lower())


def match_columns(header):
    """{variable: column index} for the recognised columns of a header row."""
    lookup = {alias: var for var, aliases in ALIASES.items() for alias in aliases}
    found = {}
    for i, col in enumerate(header):
        var = lookup.get(normalise(col))
        if var and var not in found:
            found[var] = i
    return found


def _number(text, decimal_comma):
    text = text.strip()
    if text.lower() in MISSING:
        return None
    if decimal_comma:
        text = text.replace(".", "").replace(",", ".") if text.count(",") == 1 and "." in text else text.replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        raise ValueError("'{}' is not a number".format(text))
    return None if value in (-999.0, -9999.0) else value


def _date(text):
    text = text.strip()[:10]
    m = YEAR_FIRST.match(text) or DAY_FIRST.match(text)
    if not m:
        raise ValueError("'{}' is not a date (YYYY-MM-DD or DD.MM.YYYY)".format(text))
    sep = m.group(1)
    fmt = "%Y{0}%m{0}%d" if m.re is YEAR_FIRST else "%d{0}%m{0}%Y"
    return datetime.strptime(text, fmt.format(sep)).date()


def _dialect(sample):
    first = sample.splitlines()[0] if sample else ""
    counts = {d: first.count(d) for d in (";", "\t", ",")}
    delimiter = max(counts, key=counts.get)
    if counts[delimiter] == 0:
        raise StationDataError("Cannot detect the column delimiter (use , ; or tab).")
    return delimiter


class StationRecords:
    """Daily records of one station from the CSV."""

    def __init__(self, station_id, days, columns, warnings):
        self.station_id = station_id
        self.days = days            # list of DailyClimate in date order
        self.columns = columns      # variables present in the file
        self.warnings = warnings    # data problems found while reading


def read_station_csv(text, wind_height=2.0):
    """{station id: StationRecords} from the CSV content (str).

    wind_height: measurement height [m] of a 'wind' column; converted to 2 m
    with FAO-56 Eq. 47. A 'u2' column is used as it is.
    """
    if text.startswith("﻿"):
        text = text[1:]
    delimiter = _dialect(text[:4096])
    decimal_comma = delimiter in (";", "\t")
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise StationDataError("The station file has no data rows.")
    cols = match_columns(rows[0])
    missing = [v for v in REQUIRED if v not in cols]
    if missing:
        raise StationDataError("Station file lacks required column(s): {} (found: {}).".format(
            ", ".join(missing), ", ".join(rows[0])))
    if "u2" in cols and "wind" in cols:
        del cols["wind"]
    if wind_height <= 0:
        raise StationDataError("Wind measurement height must be positive.")

    per_station, warnings = {}, {}
    for line_no, row in enumerate(rows[1:], start=2):
        row = row + [""] * (len(rows[0]) - len(row))
        sid = row[cols["station"]].strip() if "station" in cols else SINGLE_STATION
        try:
            day = _date(row[cols["date"]])
            values = {v: _number(row[i], decimal_comma) for v, i in cols.items()
                      if v not in ("station", "date")}
        except ValueError as exc:
            raise StationDataError("Line {}: {}".format(line_no, exc))
        notes = warnings.setdefault(sid, [])
        tmax, tmin = values.get("tmax"), values.get("tmin")
        if tmax is not None and tmin is not None and tmax < tmin:
            notes.append("{}: Tmax < Tmin, values swapped".format(day))
            tmax, tmin = tmin, tmax
        for v in ("rh", "rhmax", "rhmin"):
            if values.get(v) is not None and not 0 <= values[v] <= 100:
                notes.append("{}: {} = {} outside 0-100 %, ignored".format(day, v, values[v]))
                values[v] = None
        for v in ("u2", "wind", "rs", "sunshine", "precip"):
            if values.get(v) is not None and values[v] < 0:
                notes.append("{}: negative {} ignored".format(day, v))
                values[v] = None
        u2 = values.get("u2")
        if u2 is None and values.get("wind") is not None:
            u2 = values["wind"] if wind_height == 2.0 else fao56.wind_speed_2m(values["wind"], wind_height)
        rec = DailyClimate(day, tmax, tmin, values.get("tdew"), values.get("rh"), u2,
                           values.get("rs"), values.get("precip"), rhmax=values.get("rhmax"),
                           rhmin=values.get("rhmin"), sunshine=values.get("sunshine"))
        days = per_station.setdefault(sid, {})
        if day in days:
            notes.append("{}: duplicate date, last row used".format(day))
        days[day] = rec

    present = sorted(v for v in cols if v not in ("station", "date"))
    return {sid: StationRecords(sid, [days[d] for d in sorted(days)], present, warnings.get(sid, []))
            for sid, days in per_station.items()}


def read_station_file(path, wind_height=2.0):
    """read_station_csv for a file path (UTF-8, falling back to Windows-1254 for Turkish files)."""
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:          # Turkish Windows exports
        text = raw.decode("cp1254", errors="replace")
    return read_station_csv(text, wind_height)


class StationSeries:
    """Station records with location, in the shape the field chain expects (like PowerSeries)."""

    def __init__(self, station_id, latitude, longitude, elevation, days):
        self.station_id = station_id
        self.latitude = latitude
        self.longitude = longitude
        self.elevation = elevation
        self.days = days
        self.sources = ["station {}".format(station_id) if station_id else "station"]
        self.api_version = None
        self.description = "Weather station {}".format(station_id).strip()
