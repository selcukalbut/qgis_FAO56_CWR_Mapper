"""Single crop coefficient ETc, effective rainfall and net irrigation requirement.

Kc curve follows FAO-56 Chapter 6 (Fig. 25, Eq. 66): constant Kc_ini during
the initial stage, linear rise to Kc_mid during crop development, constant
Kc_mid in mid-season and linear change to Kc_end during the late season.
"""

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
