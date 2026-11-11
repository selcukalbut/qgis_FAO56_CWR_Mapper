"""Single crop coefficient ETc, effective rainfall and net irrigation requirement.

Kc curve follows FAO-56 Chapter 6 (Fig. 25, Eq. 66): constant Kc_ini during
the initial stage, linear rise to Kc_mid during crop development, constant
Kc_mid in mid-season and linear change to Kc_end during the late season.

Effective rainfall: a fixed fraction of rainfall, or the USDA Soil
Conservation Service method in two forms:
- "usda_cropwat": the simplified form used in CROPWAT (Smith 1992, FAO
  Irrigation and Drainage Paper 46), monthly rainfall only.
- "usda_neh": USDA NRCS National Engineering Handbook Part 623, Chapter 2
  (1993), Eq. 2-84 and 2-85 (from USDA 1970): monthly rainfall, monthly crop
  ET and the usable soil water storage D.
Both were developed for monthly totals. Shorter periods are scaled to a
month equivalent (period total x days in the calendar month / days in the
period), the formula is applied, and the result is scaled back; for a
10-day dekad of a 30-day month this is factor 3, as in CROPWAT's decade form.
"""

import calendar
from datetime import timedelta

STAGES = ("initial", "development", "mid", "late")


def kc_for_day(day_in_season, kc_ini, kc_mid, kc_end, l_ini, l_dev, l_mid, l_late):
    """Crop coefficient and stage name for a day in the season.

    ``day_in_season`` is 1-based (1 = planting day). Stage lengths are in days.
    Returns (kc, stage) or (None, None) outside the growing season.
    """
    i = day_in_season
    if i < 1 or i > l_ini + l_dev + l_mid + l_late:
        return None, None
    if i <= l_ini:
        return kc_ini, "initial"
    i_dev = i - l_ini
    if i_dev <= l_dev:
        return kc_ini + i_dev / l_dev * (kc_mid - kc_ini), "development"   # Eq. 66
    i_mid = i_dev - l_dev
    if i_mid <= l_mid:
        return kc_mid, "mid"
    i_late = i_mid - l_mid
    return kc_mid + i_late / l_late * (kc_end - kc_mid), "late"            # Eq. 66


def kc_series(planting_date, kc_ini, kc_mid, kc_end, l_ini, l_dev, l_mid, l_late):
    """List of (date, kc, stage) for every day of the growing season."""
    total = l_ini + l_dev + l_mid + l_late
    out = []
    for k in range(total):
        kc, stage = kc_for_day(k + 1, kc_ini, kc_mid, kc_end, l_ini, l_dev, l_mid, l_late)
        out.append((planting_date + timedelta(days=k), kc, stage))
    return out


def effective_rainfall_fixed(p, fraction=0.80):
    """Effective rainfall Pe [mm] as a fixed fraction of rainfall P [mm]."""
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be between 0 and 1")
    return max(p, 0.0) * fraction


PE_FIXED = "fixed"
PE_USDA_CROPWAT = "usda_cropwat"
PE_USDA_NEH = "usda_neh"
PE_METHODS = (PE_FIXED, PE_USDA_CROPWAT, PE_USDA_NEH)
MM_PER_INCH = 25.4


def effective_rainfall_usda_cropwat(p_month):
    """CROPWAT USDA SCS method: monthly effective rainfall [mm] from monthly rainfall [mm].

    Pe = P (125 - 0.2 P) / 125 for P <= 250 mm, Pe = 125 + 0.1 P above
    (continuous at 250 mm, Pe = 150 mm).
    """
    p = max(p_month, 0.0)
    return p * (125.0 - 0.2 * p) / 125.0 if p <= 250.0 else 125.0 + 0.1 * p


def soil_storage_factor(d_inch):
    """NEH 623 Eq. 2-85: SF = 0.531747 + 0.295164 D - 0.057697 D^2 + 0.003804 D^3, D in inches.

    The polynomial is a fit of the factors under Table 2-43 (0.72 at 0.75 in ...
    1.00 at 3 in ... 1.07 at 7 in); it differs from them by up to 0.013.
    """
    d = d_inch
    return 0.531747 + 0.295164 * d - 0.057697 * d ** 2 + 0.003804 * d ** 3


def effective_rainfall_usda_neh(p_month, etc_month, storage_mm=75.0):
    """NEH 623 Eq. 2-84 with the storage factor of Eq. 2-85; all depths in mm.

    Pe = SF (0.70917 Pt^0.82416 - 0.11556) 10^(0.02426 ETc), Pt, ETc and Pe in inches.
    Pe cannot exceed the monthly rainfall or the monthly crop ET (note under
    Table 2-43) and is not negative.
    """
    pt, etc = max(p_month, 0.0) / MM_PER_INCH, max(etc_month, 0.0) / MM_PER_INCH
    if pt <= 0.0:
        return 0.0
    pe = soil_storage_factor(storage_mm / MM_PER_INCH) * usda_neh_base_inch(pt, etc)
    return max(0.0, min(pe, pt, etc)) * MM_PER_INCH


def usda_neh_base_inch(pt, etc):
    """Eq. 2-84 without SF and without limits, in inches (the values of Table 2-43, D = 3 in)."""
    return (0.70917 * pt ** 0.82416 - 0.11556) * 10.0 ** (0.02426 * etc)


class EffectiveRainfall:
    """Effective rainfall method and its parameters."""

    def __init__(self, method=PE_FIXED, fraction=0.80, storage_mm=75.0):
        if method not in PE_METHODS:
            raise ValueError("unknown effective rainfall method: " + str(method))
        if not 0.0 <= fraction <= 1.0:
            raise ValueError("fraction must be between 0 and 1")
        if method == PE_USDA_NEH and not 0.0 < storage_mm <= 250.0:
            raise ValueError("usable soil water storage must be between 0 and 250 mm")
        self.method, self.fraction, self.storage_mm = method, fraction, storage_mm

    @property
    def per_period(self):
        """True when Pe is evaluated on period totals rather than per day."""
        return self.method != PE_FIXED

    def period(self, p, etc, days, month_days):
        """Pe [mm] for a period of `days` days in a month of `month_days` days."""
        scale = month_days / float(days)
        if self.method == PE_USDA_CROPWAT:
            return effective_rainfall_usda_cropwat(p * scale) / scale
        if self.method == PE_USDA_NEH:
            return effective_rainfall_usda_neh(p * scale, etc * scale, self.storage_mm) / scale
        return effective_rainfall_fixed(p, self.fraction)

    def describe(self):
        if self.method == PE_USDA_CROPWAT:
            return "USDA SCS (CROPWAT)"
        if self.method == PE_USDA_NEH:
            return "USDA SCS (NEH 623, D = {:g} mm)".format(self.storage_mm)
        return "fixed fraction {:.2f}".format(self.fraction)


def days_in_month(d):
    return calendar.monthrange(d.year, d.month)[1]


def net_irrigation(etc, pe):
    """Daily net irrigation requirement [mm]: max(0, ETc - Pe)."""
    return max(0.0, etc - pe)


def depth_to_volume_m3(depth_mm, area_m2):
    """Water volume [m3] from depth [mm] over an area [m2] (1 mm = 1 L m-2)."""
    return depth_mm * area_m2 / 1000.0


def volume_per_decare(depth_mm):
    """m3 per decare (1000 m2) for a depth in mm: 1 mm = 1 m3/da."""
    return depth_mm


def volume_per_hectare(depth_mm):
    """m3 per hectare for a depth in mm: 1 mm = 10 m3/ha."""
    return depth_mm * 10.0
