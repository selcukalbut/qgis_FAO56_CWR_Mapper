"""NASA POWER daily point API client (no API key required).

Request/response format verified against the live API (v2.10.1, Oct 2026):
- Endpoint: /api/temporal/daily/point, dates as YYYYMMDD, local solar time.
- With community=AG radiation is MJ m-2 day-1; other communities (RE, SB)
  return kW-hr m-2 day-1, so units are read from the response and converted.
- WS2M is already at 2 m; the third coordinate is the grid cell elevation [m].
- Missing days (including the last few days, ~3 days lag for temperature and
  ~6 for radiation, and any future dates) come back as fill_value -999.
- Invalid requests return HTTP 422 with a {"detail": [...]} body.

The module has no QGIS dependency. Network access goes through a ``fetcher``
callable (url -> bytes) so the plugin can pass a QGIS network request that
honours the user's proxy settings; the default uses urllib.
"""

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime

BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = ("T2M_MAX", "T2M_MIN", "T2MDEW", "RH2M", "WS2M",
              "ALLSKY_SFC_SW_DWN", "PRECTOTCORR")
ATTRIBUTION = ("These data were obtained from the NASA Langley Research Center "
               "(LaRC) POWER Project funded through the NASA Earth Science/"
               "Applied Science Program.")

_RADIATION_TO_MJ = {"MJ/m^2/day": 1.0, "kW-hr/m^2/day": 3.6}


class PowerError(Exception):
    """Raised when the POWER API returns an error or an unusable response."""


class DailyClimate:
    """One day of POWER data; missing values are None."""

    __slots__ = ("day", "tmax", "tmin", "tdew", "rh", "u2", "rs", "precip")

    def __init__(self, day, tmax, tmin, tdew, rh, u2, rs, precip):
        self.day = day
        self.tmax = tmax
        self.tmin = tmin
        self.tdew = tdew
        self.rh = rh
        self.u2 = u2
        self.rs = rs
        self.precip = precip

    def __repr__(self):
        return "DailyClimate({})".format(", ".join(
            "{}={!r}".format(k, getattr(self, k)) for k in self.__slots__))


class PowerSeries:
    """Parsed POWER response for one point."""

    def __init__(self, latitude, longitude, elevation, sources, days):
        self.latitude = latitude
        self.longitude = longitude
        self.elevation = elevation   # POWER grid cell elevation [m]
        self.sources = sources       # e.g. ["MERRA2", "SYN1DEG", "POWER"]
        self.days = days             # list of DailyClimate, date order

    def missing_days(self):
        """Days on which any variable needed for ETo is missing."""
        return [d.day for d in self.days
                if None in (d.tmax, d.tmin, d.u2, d.rs) or (d.tdew is None and d.rh is None)]


def build_url(latitude, longitude, start, end, community="AG"):
    """Request URL for the daily point endpoint; start/end are datetime.date."""
    if not -90.0 <= latitude <= 90.0:
        raise ValueError("latitude must be between -90 and 90")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError("longitude must be between -180 and 180")
    if end < start:
        raise ValueError("end date is before start date")
    return ("{}?parameters={}&community={}&longitude={:.4f}&latitude={:.4f}"
            "&start={}&end={}&format=JSON").format(
                BASE_URL, ",".join(PARAMETERS), community, longitude, latitude,
                start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))


def parse_response(data):
    """Build a PowerSeries from the decoded JSON response (dict)."""
    if "detail" in data:
        raise PowerError("POWER API rejected the request: {}".format(
            "; ".join(d.get("msg", str(d)) for d in data["detail"])))
    try:
        lon, lat, elevation = data["geometry"]["coordinates"][:3]
        params = data["properties"]["parameter"]
        header = data["header"]
    except (KeyError, TypeError, ValueError) as exc:
        raise PowerError("Unexpected POWER response format") from exc

    fill = header.get("fill_value", -999.0)
    missing = [p for p in PARAMETERS if p not in params]
    if missing:
        raise PowerError("POWER response lacks parameters: " + ", ".join(missing))

    units = data.get("parameters", {}).get("ALLSKY_SFC_SW_DWN", {}).get("units", "MJ/m^2/day")
    if units not in _RADIATION_TO_MJ:
        raise PowerError("Unsupported radiation unit: " + units)
    rad_factor = _RADIATION_TO_MJ[units]

    def value(name, key, factor=1.0):
        v = params[name].get(key)
        return None if v is None or v == fill else v * factor

    days = []
    for key in sorted(params["T2M_MAX"]):
        days.append(DailyClimate(
            day=datetime.strptime(key, "%Y%m%d").date(),
            tmax=value("T2M_MAX", key),
            tmin=value("T2M_MIN", key),
            tdew=value("T2MDEW", key),
            rh=value("RH2M", key),
            u2=value("WS2M", key),
            rs=value("ALLSKY_SFC_SW_DWN", key, rad_factor),
            precip=value("PRECTOTCORR", key),
        ))
    return PowerSeries(lat, lon, elevation, header.get("sources", []), days)


def urllib_fetcher(url, timeout=60):
    """Default fetcher. Returns the body for HTTP 200 and 422 (error JSON)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            return exc.read()
        raise PowerError("POWER API HTTP error {}".format(exc.code)) from exc
    except urllib.error.URLError as exc:
        raise PowerError("Cannot reach POWER API: {}".format(exc.reason)) from exc


def _cache_path(cache_dir, latitude, longitude, start, end):
    name = "power_{:.4f}_{:.4f}_{}_{}.json".format(
        latitude, longitude, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
    return os.path.join(cache_dir, name)


def fetch(latitude, longitude, start, end, fetcher=None, cache_dir=None, today=None):
    """Download (or read from cache) daily POWER data for one point.

    Start dates in the future are rejected. Responses that still contain
    missing values are not cached, so recent days are fetched again once
    POWER has filled them in.
    """
    today = today or date.today()
    if start > today:
        raise ValueError("Start date {} is in the future; POWER has no data for it.".format(start))

    path = _cache_path(cache_dir, latitude, longitude, start, end) if cache_dir else None
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return parse_response(json.load(fh))

    body = (fetcher or urllib_fetcher)(build_url(latitude, longitude, start, end))
    try:
        data = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    except ValueError as exc:
        raise PowerError("POWER API returned invalid JSON") from exc
    series = parse_response(data)

    if path and not series.missing_days():
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    return series
