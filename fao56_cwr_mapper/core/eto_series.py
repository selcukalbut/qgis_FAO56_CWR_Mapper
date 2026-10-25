"""Daily ETo time series from gridded or station climate records.

Records are any objects with the attributes ``day, tmax, tmin, tdew, rh, u2,
rs, precip`` (e.g. nasa_power.DailyClimate); missing values are None.
"""

from . import fao56

EA_TDEW = "tdew"      # FAO-56 Eq. 14 (preferred when dewpoint is available)
EA_RHMEAN = "rhmean"  # FAO-56 Eq. 19


def actual_vapour_pressure(rec):
    """Return (ea, method) for a record, or (None, None) if humidity is missing."""
    if rec.tdew is not None:
        return fao56.actual_vapour_pressure_from_tdew(rec.tdew), EA_TDEW
    if rec.rh is not None and rec.tmax is not None and rec.tmin is not None:
        return fao56.actual_vapour_pressure_from_rhmean(rec.tmax, rec.tmin, rec.rh), EA_RHMEAN
    return None, None


def daily_eto_series(records, latitude, elevation):
    """List of dicts (one per record) with ETo and its intermediate values.

    Days with missing inputs get ``ETo = None`` and ``missing = True`` so
    that they can be counted and reported instead of silently skipped.
    """
    out = []
    for rec in records:
        ea, method = actual_vapour_pressure(rec)
        if None in (ea, rec.tmax, rec.tmin, rec.u2, rec.rs):
            out.append({"day": rec.day, "ETo": None, "missing": True,
                        "precip": rec.precip, "ea_method": method})
            continue
        row = fao56.daily_eto(rec.day, latitude, elevation,
                              rec.tmax, rec.tmin, rec.u2, ea, rec.rs)
        row.update({"day": rec.day, "missing": False,
                    "precip": rec.precip, "ea_method": method})
        out.append(row)
    return out
