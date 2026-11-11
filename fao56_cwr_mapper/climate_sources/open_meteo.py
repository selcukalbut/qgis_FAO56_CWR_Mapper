"""Open-Meteo Historical Weather API client (no QGIS dependency, no API key).

Verified against the documentation and the live API (Nov 2026):
- Endpoint https://archive-api.open-meteo.com/v1/archive, dates YYYY-MM-DD,
  daily values aggregated in the local time zone (timezone=auto).
- Daily variables used: temperature_2m_max/min, dew_point_2m_mean,
  relative_humidity_2m_mean, wind_speed_10m_mean (m/s with wind_speed_unit=ms,
  at 10 m), shortwave_radiation_sum (MJ m-2), precipitation_sum (mm) and,
  for comparison only, et0_fao_evapotranspiration (mm).
- Models: era5_seamless (default; ERA5-Land 0.1 deg temperature and humidity
  with ERA5 wind and radiation), era5 (0.25 deg), best_match (blends ECMWF IFS
  9 km and ERA5; recent days without delay). era5_land alone has no wind and
  radiation, so it is not offered. ERA5 data arrive with about 5 days delay;
  missing days come back as null.
- The response gives the grid cell centre and the point elevation from a
  90 m DEM, to which temperatures are downscaled.
- Errors: HTTP 400 with {"error": true, "reason": "..."}.

Terms: the free API may only be used for non-commercial purposes; data are
CC BY 4.0 and must be credited (see TERMS and ATTRIBUTION).
"""

import json
import os
from datetime import date, datetime

from ..core import fao56
from ..core.climate import DailyClimate

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY = ("temperature_2m_max", "temperature_2m_min", "dew_point_2m_mean",
         "relative_humidity_2m_mean", "wind_speed_10m_mean", "shortwave_radiation_sum",
         "precipitation_sum", "et0_fao_evapotranspiration")
MODELS = ("era5_seamless", "era5", "best_match")
MODEL_NAMES = {"era5_seamless": "ERA5-Seamless", "era5": "ERA5", "best_match": "Best match"}
EXPECTED_UNITS = {"temperature_2m_max": "°C", "temperature_2m_min": "°C", "dew_point_2m_mean": "°C",
                  "relative_humidity_2m_mean": "%", "wind_speed_10m_mean": "m/s",
                  "shortwave_radiation_sum": "MJ/m²", "precipitation_sum": "mm"}
WIND_HEIGHT = 10.0
ATTRIBUTION = ("Weather data by Open-Meteo.com (https://open-meteo.com/), licensed under CC BY 4.0. "
               "Generated using Copernicus Climate Change Service information.")
TERMS = ("The free Open-Meteo API may only be used for non-commercial purposes "
         "(https://open-meteo.com/en/terms); commercial users need an Open-Meteo subscription "
         "or another climate source.")


class OpenMeteoError(Exception):
    """Raised when Open-Meteo returns an error or an unusable response."""


class OpenMeteoSeries:
    """Parsed response for one point, in the shape the field chain expects."""

    def __init__(self, latitude, longitude, elevation, model, days, reference_eto):
        self.latitude = latitude        # grid cell centre
        self.longitude = longitude
        self.elevation = elevation      # point elevation (90 m DEM)
        self.model = model
        self.days = days
        self.reference_eto = reference_eto   # {date: Open-Meteo FAO ET0}, for comparison only
        self.sources = ["Open-Meteo {}".format(MODEL_NAMES.get(model, model))]
        self.api_version = None
        self.attribution = ATTRIBUTION
        self.description = "Open-Meteo {} ({:.2f}, {:.2f})".format(
            MODEL_NAMES.get(model, model), latitude, longitude)

    def missing_days(self):
        return [d.day for d in self.days
                if None in (d.tmax, d.tmin, d.u2, d.rs) or (d.tdew is None and d.rh is None)]


def request_coordinates(latitude, longitude):
    """Coordinates as sent in the request; 0.01 deg (about 1 km) so nearby fields share a request."""
    return round(latitude, 2), round(longitude, 2)


def build_url(latitude, longitude, start, end, model="era5_seamless"):
    if not -90.0 <= latitude <= 90.0:
        raise ValueError("latitude must be between -90 and 90")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError("longitude must be between -180 and 180")
    if end < start:
        raise ValueError("end date is before start date")
    if model not in MODELS:
        raise ValueError("unknown Open-Meteo model: " + model)
    lat, lon = request_coordinates(latitude, longitude)
    return ("{}?latitude={:.2f}&longitude={:.2f}&start_date={}&end_date={}&daily={}"
            "&wind_speed_unit=ms&timezone=auto&models={}").format(
                BASE_URL, lat, lon, start.isoformat(), end.isoformat(), ",".join(DAILY), model)


def parse_response(data, model="era5_seamless"):
    if data.get("error"):
        raise OpenMeteoError("Open-Meteo rejected the request: {}".format(data.get("reason", "")))
    try:
        lat, lon, elevation = data["latitude"], data["longitude"], data["elevation"]
        daily, units = data["daily"], data["daily_units"]
        times = daily["time"]
    except (KeyError, TypeError) as exc:
        raise OpenMeteoError("Unexpected Open-Meteo response format") from exc
    missing = [v for v in DAILY if v not in daily]
    if missing:
        raise OpenMeteoError("Open-Meteo response lacks: " + ", ".join(missing))
    wrong = ["{} in {}".format(v, units.get(v)) for v, u in EXPECTED_UNITS.items() if units.get(v) != u]
    if wrong:
        raise OpenMeteoError("Unexpected Open-Meteo units: " + ", ".join(wrong))

    days, reference = [], {}
    for i, t in enumerate(times):
        day = datetime.strptime(t, "%Y-%m-%d").date()

        def value(name):
            return daily[name][i]
        wind = value("wind_speed_10m_mean")
        days.append(DailyClimate(
            day, value("temperature_2m_max"), value("temperature_2m_min"), value("dew_point_2m_mean"),
            value("relative_humidity_2m_mean"),
            None if wind is None else fao56.wind_speed_2m(wind, WIND_HEIGHT),    # Eq. 47
            value("shortwave_radiation_sum"), value("precipitation_sum")))
        reference[day] = value("et0_fao_evapotranspiration")
    return OpenMeteoSeries(lat, lon, elevation, model, days, reference)


def _cache_path(cache_dir, latitude, longitude, start, end, model):
    lat, lon = request_coordinates(latitude, longitude)
    return os.path.join(cache_dir, "openmeteo_{}_{:.2f}_{:.2f}_{}_{}.json".format(
        model, lat, lon, start.strftime("%Y%m%d"), end.strftime("%Y%m%d")))


def fetch(latitude, longitude, start, end, model="era5_seamless", fetcher=None, cache_dir=None,
          today=None):
    """Download (or read from cache) daily data for one point.

    fetcher: callable(url) -> bytes, returning the body for HTTP 200 and 400.
    Responses that still contain missing values are not cached.
    """
    today = today or date.today()
    if start > today:
        raise ValueError("Start date {} is in the future; Open-Meteo has no data for it.".format(start))
    path = _cache_path(cache_dir, latitude, longitude, start, end, model) if cache_dir else None
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return parse_response(json.load(fh), model)
    if fetcher is None:
        raise ValueError("A fetcher is required to download Open-Meteo data.")
    body = fetcher(build_url(latitude, longitude, start, end, model))
    try:
        data = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    except ValueError as exc:
        raise OpenMeteoError("Open-Meteo returned invalid JSON") from exc
    series = parse_response(data, model)
    if path and not series.missing_days():
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    return series
