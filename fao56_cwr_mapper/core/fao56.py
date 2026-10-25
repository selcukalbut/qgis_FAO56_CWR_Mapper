"""FAO-56 Penman-Monteith reference evapotranspiration (daily time step).

Each function implements one equation from Allen et al. (1998), FAO Irrigation
and Drainage Paper No. 56, so that every intermediate value can be checked
against the worked examples in Chapters 3-4. Equation numbers refer to FAO-56.

Units: temperature degC, pressure kPa, radiation MJ m-2 day-1, wind m s-1,
elevation m, latitude in decimal degrees (north positive).
"""

import math
from datetime import date

SOLAR_CONSTANT = 0.0820      # Gsc, MJ m-2 min-1
STEFAN_BOLTZMANN = 4.903e-9  # sigma, MJ K-4 m-2 day-1
ALBEDO_GRASS = 0.23          # reference crop albedo


# --- Atmospheric parameters (Chapter 3) -------------------------------------

def atmospheric_pressure(elevation):
    """Eq. 7: atmospheric pressure P [kPa] from elevation z [m]."""
    return 101.3 * ((293.0 - 0.0065 * elevation) / 293.0) ** 5.26


def psychrometric_constant(pressure):
    """Eq. 8: psychrometric constant gamma [kPa degC-1]."""
    return 0.665e-3 * pressure


# --- Air humidity -----------------------------------------------------------

def saturation_vapour_pressure(t):
    """Eq. 11: saturation vapour pressure e°(T) [kPa]."""
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))


def mean_saturation_vapour_pressure(tmax, tmin):
    """Eq. 12: mean saturation vapour pressure es [kPa]."""
    return (saturation_vapour_pressure(tmax) + saturation_vapour_pressure(tmin)) / 2.0


def slope_vapour_pressure_curve(t):
    """Eq. 13: slope of saturation vapour pressure curve Delta [kPa degC-1]."""
    return 4098.0 * saturation_vapour_pressure(t) / (t + 237.3) ** 2


def actual_vapour_pressure_from_tdew(tdew):
    """Eq. 14: actual vapour pressure ea [kPa] from dewpoint temperature."""
    return saturation_vapour_pressure(tdew)


def actual_vapour_pressure_from_rhmin_rhmax(tmax, tmin, rhmax, rhmin):
    """Eq. 17: ea [kPa] from RHmax and RHmin [%]."""
    return (saturation_vapour_pressure(tmin) * rhmax / 100.0
            + saturation_vapour_pressure(tmax) * rhmin / 100.0) / 2.0


def actual_vapour_pressure_from_rhmax(tmin, rhmax):
    """Eq. 18: ea [kPa] from RHmax only (when RHmin is unreliable)."""
    return saturation_vapour_pressure(tmin) * rhmax / 100.0


def actual_vapour_pressure_from_rhmean(tmax, tmin, rhmean):
    """Eq. 19: ea [kPa] from mean relative humidity [%]."""
    return rhmean / 100.0 * mean_saturation_vapour_pressure(tmax, tmin)


# --- Radiation --------------------------------------------------------------

def day_of_year(d):
    """J: day number in the year (1 = 1 January)."""
    return d.timetuple().tm_yday


def inverse_relative_distance(j):
    """Eq. 23: inverse relative Earth-Sun distance dr [-]."""
    return 1.0 + 0.033 * math.cos(2.0 * math.pi / 365.0 * j)


def solar_declination(j):
    """Eq. 24: solar declination delta [rad]."""
    return 0.409 * math.sin(2.0 * math.pi / 365.0 * j - 1.39)


def sunset_hour_angle(lat_rad, declination):
    """Eq. 25: sunset hour angle omega_s [rad].

    The arccos argument is clipped to [-1, 1] so that polar day (pi) and
    polar night (0) are handled instead of raising a math domain error.
    """
    x = -math.tan(lat_rad) * math.tan(declination)
    return math.acos(max(-1.0, min(1.0, x)))


def extraterrestrial_radiation(latitude, j):
    """Eq. 21: extraterrestrial radiation Ra [MJ m-2 day-1]."""
    phi = math.radians(latitude)
    dr = inverse_relative_distance(j)
    delta = solar_declination(j)
    ws = sunset_hour_angle(phi, delta)
    return (24.0 * 60.0 / math.pi * SOLAR_CONSTANT * dr
            * (ws * math.sin(phi) * math.sin(delta)
               + math.cos(phi) * math.cos(delta) * math.sin(ws)))


def daylight_hours(latitude, j):
    """Eq. 34: maximum possible duration of sunshine N [hour]."""
    ws = sunset_hour_angle(math.radians(latitude), solar_declination(j))
    return 24.0 / math.pi * ws


def solar_radiation_from_sunshine(n, daylight, ra, a_s=0.25, b_s=0.50):
    """Eq. 35 (Angstrom): solar radiation Rs [MJ m-2 day-1] from sunshine hours n."""
    return (a_s + b_s * n / daylight) * ra


def clear_sky_radiation(ra, elevation):
    """Eq. 37: clear-sky solar radiation Rso [MJ m-2 day-1]."""
    return (0.75 + 2e-5 * elevation) * ra


def net_shortwave_radiation(rs, albedo=ALBEDO_GRASS):
    """Eq. 38: net solar (shortwave) radiation Rns [MJ m-2 day-1]."""
    return (1.0 - albedo) * rs


def net_longwave_radiation(tmax, tmin, ea, rs, rso):
    """Eq. 39: net outgoing longwave radiation Rnl [MJ m-2 day-1].

    Rs/Rso is limited to 1.0 as required by FAO-56.
    """
    tmax_k4 = (tmax + 273.16) ** 4
    tmin_k4 = (tmin + 273.16) ** 4
    ratio = min(rs / rso, 1.0) if rso > 0 else 1.0
    return (STEFAN_BOLTZMANN * (tmax_k4 + tmin_k4) / 2.0
            * (0.34 - 0.14 * math.sqrt(ea))
            * (1.35 * ratio - 0.35))


def net_radiation(rns, rnl):
    """Eq. 40: net radiation Rn [MJ m-2 day-1]."""
    return rns - rnl


# --- Wind -------------------------------------------------------------------

def wind_speed_2m(uz, height):
    """Eq. 47: wind speed at 2 m [m s-1] from measurement at height z [m]."""
    return uz * 4.87 / math.log(67.8 * height - 5.42)


# --- Penman-Monteith ----------------------------------------------------------

def eto_penman_monteith(t_mean, u2, es, ea, delta, gamma, rn, g=0.0):
    """Eq. 6: FAO-56 Penman-Monteith reference evapotranspiration ETo [mm day-1]."""
    num = (0.408 * delta * (rn - g)
           + gamma * 900.0 / (t_mean + 273.0) * u2 * (es - ea))
    den = delta + gamma * (1.0 + 0.34 * u2)
    return num / den


def daily_eto(day, latitude, elevation, tmax, tmin, u2, ea, rs):
    """Daily ETo [mm day-1] from the minimum data set used by gridded sources.

    ``day`` is a ``datetime.date``; ``ea`` [kPa] must already be derived with
    one of the actual_vapour_pressure_* functions and ``u2`` reduced to 2 m.
    Soil heat flux G is taken as 0 for the daily step (FAO-56 Eq. 42).
    Returns a dict with ETo and all intermediate values for traceability.
    """
    if not isinstance(day, date):
        raise TypeError("day must be a datetime.date")
    j = day_of_year(day)
    t_mean = (tmax + tmin) / 2.0                     # Eq. 9
    pressure = atmospheric_pressure(elevation)
    gamma = psychrometric_constant(pressure)
    delta = slope_vapour_pressure_curve(t_mean)
    es = mean_saturation_vapour_pressure(tmax, tmin)
    ra = extraterrestrial_radiation(latitude, j)
    rso = clear_sky_radiation(ra, elevation)
    rns = net_shortwave_radiation(rs)
    rnl = net_longwave_radiation(tmax, tmin, ea, rs, rso)
    rn = net_radiation(rns, rnl)
    eto = eto_penman_monteith(t_mean, u2, es, ea, delta, gamma, rn)
    return {
        "J": j, "t_mean": t_mean, "P": pressure, "gamma": gamma,
        "delta": delta, "es": es, "ea": ea, "vpd": es - ea,
        "Ra": ra, "Rs": rs, "Rso": rso, "Rns": rns, "Rnl": rnl, "Rn": rn,
        "u2": u2, "ETo": max(eto, 0.0),
    }
