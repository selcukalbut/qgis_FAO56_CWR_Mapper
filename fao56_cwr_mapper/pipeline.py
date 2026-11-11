"""Point/field calculation chain, independent of QGIS.

Climate (NASA POWER, Open-Meteo or station) -> FAO-56 ETo -> Kc x ETo = ETc -> Pe -> net irrigation.
The QGIS layer/Processing code calls ``run_field`` once per field centroid.
"""

from datetime import date

from .climate_sources import nasa_power
from .core import eto_series, field_balance, weighting


def run_field(latitude, longitude, kc_crop, stage, planting_date, area_m2=None,
              elevation=None, pe_fraction=0.80, nir_period=field_balance.NIR_DEKAD,
              efficiency=None, fetcher=None, cache_dir=None, today=None, series=None,
              estimation=None):
    """Full chain for one location.

    elevation: site elevation [m]; defaults to the POWER grid cell elevation,
    which is consistent with the gridded meteorology.
    series: an already downloaded nasa_power.PowerSeries for the same grid cell
    (see nasa_power.cell_key) or a station_csv.StationSeries covering the season;
    otherwise NASA POWER data are fetched.
    estimation: eto_series.Estimation for missing inputs (station data), or None.
    ETo always uses this location's own latitude.
    Returns the field_balance result with source details added to the summary.
    """
    today = today or date.today()
    start, end = field_balance.season_dates(planting_date, stage)
    if start > today:
        raise ValueError("Planting date {} is in the future; climate data is only "
                         "available for past days.".format(start))
    if series is None:
        series = nasa_power.fetch(latitude, longitude, start, min(end, today),
                                  fetcher=fetcher, cache_dir=cache_dir, today=today)
    z = series.elevation if elevation is None else elevation
    eto_rows = eto_series.daily_eto_series(series.days, latitude, z, estimation=estimation)
    result = field_balance.field_water_balance(
        eto_rows, kc_crop, stage, planting_date, area_m2=area_m2,
        pe_fraction=pe_fraction, nir_period=nir_period, efficiency=efficiency, today=today)
    result["summary"].update({
        "latitude": latitude, "longitude": longitude, "elevation_m": z,
        "climate_source": getattr(series, "description", None)
        or "NASA POWER daily ({})".format(", ".join(series.sources)),
        "climate_grid_elevation_m": series.elevation,
        "climate_sources": list(series.sources), "climate_api_version": series.api_version,
        "attribution": getattr(series, "attribution",
                               None if hasattr(series, "station_id") else nasa_power.ATTRIBUTION),
    })
    reference = getattr(series, "reference_eto", None)
    if reference:
        # The data provider's own FAO ETo over the computed season days, for comparison only
        days = [r["day"] for r in eto_rows if not r["missing"] and start <= r["day"] <= min(end, today)]
        values = [reference.get(d) for d in days]
        result["summary"]["reference_eto_mm"] = (sum(values) if values and None not in values else None)
    return result


def run_field_weighted(latitude, longitude, kc_crop, stage, planting_date, weighted_series,
                       area_m2=None, pe_fraction=0.80, nir_period=field_balance.NIR_DEKAD,
                       efficiency=None, today=None, estimation=None):
    """Field chain with Thiessen-weighted stations.

    weighted_series: [(weight, StationSeries)]; weights are normalised to sum to 1.
    Each station's daily ETo uses this field's latitude and the station's elevation;
    the field's daily ETo and rainfall are weighted means (core.weighting).
    """
    today = today or date.today()
    start, _ = field_balance.season_dates(planting_date, stage)
    if start > today:
        raise ValueError("Planting date {} is in the future; climate data is only "
                         "available for past days.".format(start))
    weights = weighting.normalise_weights([(i, w) for i, (w, _) in enumerate(weighted_series)])
    parts = []
    for i, w in weights:
        series = weighted_series[i][1]
        rows = eto_series.daily_eto_series(series.days, latitude, series.elevation, estimation=estimation)
        parts.append((w, series, rows))
    combined = weighting.combine_eto_rows([(w, rows) for w, _, rows in parts])
    result = field_balance.field_water_balance(
        combined, kc_crop, stage, planting_date, area_m2=area_m2,
        pe_fraction=pe_fraction, nir_period=nir_period, efficiency=efficiency, today=today)
    label = ", ".join("{} {:.0f} %".format(s.station_id or "station", 100 * w)
                      for w, s, _ in sorted(parts, key=lambda p: -p[0]))
    result["summary"].update({
        "latitude": latitude, "longitude": longitude,
        "elevation_m": sum(w * s.elevation for w, s, _ in parts),
        "climate_source": "Thiessen-weighted stations: " + label,
        "climate_grid_elevation_m": None,
        "climate_sources": sorted({src for _, s, _ in parts for src in s.sources}),
        "climate_api_version": None, "attribution": None,
        "station_weights": [(s.station_id, w) for w, s, _ in parts],
    })
    return result
