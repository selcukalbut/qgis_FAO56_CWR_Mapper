"""Point/field calculation chain, independent of QGIS.

NASA POWER daily data -> FAO-56 ETo -> Kc x ETo = ETc -> Pe -> net irrigation.
The QGIS layer/Processing code calls ``run_field`` once per field centroid.
"""

from datetime import date

from .climate_sources import nasa_power
from .core import eto_series, field_balance


def run_field(latitude, longitude, kc_crop, stage, planting_date, area_m2=None,
              elevation=None, pe_fraction=0.80, nir_period=field_balance.NIR_DEKAD,
              efficiency=None, fetcher=None, cache_dir=None, today=None):
    """Full chain for one location.

    elevation: site elevation [m]; defaults to the POWER grid cell elevation,
    which is consistent with the gridded meteorology.
    Returns the field_balance result with source details added to the summary.
    """
    today = today or date.today()
    start, end = field_balance.season_dates(planting_date, stage)
    if start > today:
        raise ValueError("Planting date {} is in the future; climate data is only "
                         "available for past days.".format(start))
    series = nasa_power.fetch(latitude, longitude, start, min(end, today),
                              fetcher=fetcher, cache_dir=cache_dir, today=today)
    z = series.elevation if elevation is None else elevation
    eto_rows = eto_series.daily_eto_series(series.days, latitude, z)
    result = field_balance.field_water_balance(
        eto_rows, kc_crop, stage, planting_date, area_m2=area_m2,
        pe_fraction=pe_fraction, nir_period=nir_period, efficiency=efficiency, today=today)
    result["summary"].update({
        "latitude": latitude, "longitude": longitude, "elevation_m": z,
        "climate_source": "NASA POWER daily ({})".format(", ".join(series.sources)),
        "climate_grid_elevation_m": series.elevation,
        "climate_sources": list(series.sources), "climate_api_version": series.api_version,
        "attribution": nasa_power.ATTRIBUTION,
    })
    return result
