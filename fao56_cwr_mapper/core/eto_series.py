"""Daily ETo time series from gridded or station climate records.

Records are core.climate.DailyClimate objects (or anything with the same
attributes); missing values are None.

Each input is taken from the best available data, in FAO-56 order:
- actual vapour pressure: dewpoint (Eq. 14), RHmax + RHmin (Eq. 17), RHmax
  (Eq. 18), mean RH (Eq. 19);
- solar radiation: measured Rs, else sunshine duration (Angstrom, Eq. 35);
- wind: measured u2.
When an ``Estimation`` is given, missing inputs are estimated with the FAO-56
procedures for missing climatic data (Chapter 3): ea from Tmin (Eq. 48), Rs from
the temperature range (Hargreaves, Eq. 50), u2 = 2 m/s. Every estimate is listed
in the row's ``estimated`` field. Without an Estimation such days are missing.
"""

from . import fao56

EA_TDEW = "tdew"        # Eq. 14 (preferred)
EA_RHMAX_RHMIN = "rhmax_rhmin"   # Eq. 17
EA_RHMAX = "rhmax"      # Eq. 18
EA_RHMEAN = "rhmean"    # Eq. 19
EA_TMIN = "tmin"        # Eq. 48, estimate

RS_MEASURED = "measured"
RS_SUNSHINE = "sunshine"     # Eq. 35
RS_TEMPERATURE = "temperature"   # Eq. 50, estimate

EST_EA = "ea from Tmin (Eq. 48)"
EST_RS = "Rs from Tmax - Tmin (Eq. 50)"
EST_U2 = "u2 = 2 m/s"


class Estimation:
    """Which missing inputs may be estimated, and with which coefficients."""

    def __init__(self, humidity=True, radiation=True, wind=True, krs=0.16, default_u2=2.0):
        self.humidity = humidity
        self.radiation = radiation
        self.wind = wind
        self.krs = krs              # 0.16 interior, 0.19 coastal (FAO-56 Eq. 50)
        self.default_u2 = default_u2


def actual_vapour_pressure(rec, estimation=None):
    """Return (ea, method) for a record, or (None, None) if humidity is missing."""
    if rec.tdew is not None:
        return fao56.actual_vapour_pressure_from_tdew(rec.tdew), EA_TDEW
    if rec.tmax is None or rec.tmin is None:
        return None, None
    rhmax, rhmin = getattr(rec, "rhmax", None), getattr(rec, "rhmin", None)
    if rhmax is not None and rhmin is not None:
        return fao56.actual_vapour_pressure_from_rhmin_rhmax(rec.tmax, rec.tmin, rhmax, rhmin), EA_RHMAX_RHMIN
    if rhmax is not None:
        return fao56.actual_vapour_pressure_from_rhmax(rec.tmin, rhmax), EA_RHMAX
    if rec.rh is not None:
        return fao56.actual_vapour_pressure_from_rhmean(rec.tmax, rec.tmin, rec.rh), EA_RHMEAN
    if estimation is not None and estimation.humidity:
        return fao56.saturation_vapour_pressure(rec.tmin), EA_TMIN      # Eq. 48: Tdew ~ Tmin
    return None, None


def solar_radiation(rec, latitude, estimation=None):
    """Return (Rs, method) for a record, or (None, None) if it cannot be derived."""
    if rec.rs is not None:
        return rec.rs, RS_MEASURED
    j = fao56.day_of_year(rec.day)
    ra = fao56.extraterrestrial_radiation(latitude, j)
    sunshine = getattr(rec, "sunshine", None)
    if sunshine is not None:
        n_max = fao56.daylight_hours(latitude, j)
        if n_max > 0:
            return fao56.solar_radiation_from_sunshine(min(sunshine, n_max), n_max, ra), RS_SUNSHINE
    if (estimation is not None and estimation.radiation
            and rec.tmax is not None and rec.tmin is not None):
        return fao56.solar_radiation_from_temperature(rec.tmax, rec.tmin, ra, estimation.krs), RS_TEMPERATURE
    return None, None


def daily_eto_series(records, latitude, elevation, estimation=None):
    """List of dicts (one per record) with ETo and its intermediate values.

    Days with missing inputs get ``ETo = None`` and ``missing = True`` so
    that they can be counted and reported instead of silently skipped.
    """
    out = []
    for rec in records:
        estimated = []
        ea, ea_method = actual_vapour_pressure(rec, estimation)
        if ea_method == EA_TMIN:
            estimated.append(EST_EA)
        rs, rs_method = solar_radiation(rec, latitude, estimation)
        if rs_method == RS_TEMPERATURE:
            estimated.append(EST_RS)
        u2 = rec.u2
        if u2 is None and estimation is not None and estimation.wind:
            u2 = estimation.default_u2
            estimated.append(EST_U2)
        base = {"day": rec.day, "precip": rec.precip, "ea_method": ea_method,
                "rs_method": rs_method, "estimated": estimated}
        if None in (ea, rec.tmax, rec.tmin, u2, rs):
            out.append(dict(base, ETo=None, missing=True))
            continue
        row = fao56.daily_eto(rec.day, latitude, elevation, rec.tmax, rec.tmin, u2, ea, rs)
        row.update(base, missing=False)
        out.append(row)
    return out
