"""Crop water requirement and net irrigation requirement for one field.

Chain: daily ETo (eto_series) x daily Kc (crop + stage lengths) = ETc;
effective rainfall Pe from daily rainfall; net irrigation requirement
NIR = max(0, ETc - Pe), evaluated per day or per dekad.

- "dekad" (default; 10-day periods, as in CROPWAT): ETc and Pe are summed
  per dekad before the difference is taken, allowing rain to cover demand
  within the same dekad.
- "daily" (option; planning draft v0.1): rain on one day cannot offset demand
  on another day, so NIR is higher, especially in wet seasons.

Neither includes soil water storage; that is the v0.3 soil water balance.
Days without climate data are never filled: they are counted, left out of
the totals and reported as warnings.
"""

from datetime import date, timedelta

from . import water_balance

NIR_DAILY = "daily"
NIR_DEKAD = "dekad"


def season_dates(planting_date, stage):
    """First and last day of the growing season for a StageLengths option."""
    return planting_date, planting_date + timedelta(days=stage.total - 1)


def dekad_of(d):
    """Dekad label 'YYYY-MM-D1/D2/D3' (days 1-10, 11-20, 21-end of month)."""
    return "{:%Y-%m}-D{}".format(d, min((d.day - 1) // 10 + 1, 3))


def month_of(d):
    return "{:%Y-%m}".format(d)


def _sum(values):
    return sum(v for v in values if v is not None)


def field_water_balance(eto_rows, kc_crop, stage, planting_date, area_m2=None,
                        pe_fraction=0.80, nir_period=NIR_DEKAD, efficiency=None,
                        today=None):
    """Daily, dekad, monthly and seasonal crop water and irrigation figures.

    eto_rows: output of eto_series.daily_eto_series (dicts with day, ETo, precip).
    kc_crop: crop_table.CropKc; stage: stage_table.StageLengths.
    area_m2: field area (ellipsoidal) for volumes; None gives depths only.
    efficiency: irrigation application efficiency (0-1) for gross requirement.
    """
    if nir_period not in (NIR_DAILY, NIR_DEKAD):
        raise ValueError("nir_period must be 'daily' or 'dekad'")
    if efficiency is not None and not 0.0 < efficiency <= 1.0:
        raise ValueError("efficiency must be between 0 and 1")
    today = today or date.today()

    climate = {r["day"]: r for r in eto_rows}
    series = water_balance.kc_series(planting_date, kc_crop.kc_ini, kc_crop.kc_mid,
                                     kc_crop.kc_end, *stage.lengths)
    daily = []
    for day, kc, stage_name in series:
        r = climate.get(day)
        eto = r["ETo"] if r else None
        p = r["precip"] if r else None
        complete = eto is not None and p is not None
        etc = kc * eto if eto is not None else None
        pe = water_balance.effective_rainfall_fixed(p, pe_fraction) if p is not None else None
        daily.append({
            "day": day, "dekad": dekad_of(day), "stage": stage_name, "Kc": kc,
            "ETo": eto, "ETc": etc, "P": p, "Pe": pe,
            "NIR": water_balance.net_irrigation(etc, pe) if complete else None,
            "missing": not complete, "no_data": r is None,
        })

    periods = {"dekad": _aggregate(daily, "dekad"),
               "month": _aggregate(daily, lambda d: month_of(d["day"]))}
    if nir_period == NIR_DEKAD:
        for d in daily:                 # daily NIR is not defined in dekad mode
            d["NIR"] = None
    else:                               # dekad NIR = sum of daily NIR
        for p in periods["dekad"]:
            if p["NIR"] is not None:
                p["NIR"] = _sum(d["NIR"] for d in daily if d["dekad"] == p["period"])
    nir_total = _sum(p["NIR"] for p in periods["dekad"])
    for p in periods["month"]:          # monthly NIR follows the chosen period
        p["NIR"] = _sum(x["NIR"] for x in periods["dekad"] if x["period"].startswith(p["period"]))

    peak = max(periods["dekad"], key=lambda p: p["NIR"] if p["NIR"] is not None else -1,
               default=None)
    summary = {
        "season_start": series[0][0], "season_end": series[-1][0], "season_days": len(series),
        "ETo_mm": _sum(d["ETo"] for d in daily), "ETc_mm": _sum(d["ETc"] for d in daily),
        "P_mm": _sum(d["P"] for d in daily), "Pe_mm": _sum(d["Pe"] for d in daily),
        "NIR_mm": nir_total, "nir_period": nir_period, "pe_fraction": pe_fraction,
        "peak_dekad": peak["period"] if peak and peak["NIR"] else None,
        "peak_dekad_NIR_mm": peak["NIR"] if peak else None,
        "missing_days": sum(d["missing"] for d in daily),
        "crop": kc_crop.name, "stage_option": stage.label,
    }
    summary.update(volumes(nir_total, area_m2))
    if efficiency is not None:
        summary["efficiency"] = efficiency
        summary["GIR_mm"] = nir_total / efficiency
    summary["warnings"] = _warnings(daily, summary, today)
    return {"daily": daily, "dekad": periods["dekad"], "month": periods["month"],
            "summary": summary}


def _aggregate(daily, key):
    groups = {}
    for d in daily:
        k = key(d) if callable(key) else d[key]
        groups.setdefault(k, []).append(d)
    out = []
    for k, days in groups.items():
        complete = all(not d["missing"] for d in days)
        etc, pe = _sum(d["ETc"] for d in days), _sum(d["Pe"] for d in days)
        out.append({"period": k, "days": len(days),
                    "missing_days": sum(d["missing"] for d in days),
                    "ETo": _sum(d["ETo"] for d in days), "ETc": etc,
                    "P": _sum(d["P"] for d in days), "Pe": pe,
                    # incomplete periods get no NIR rather than an underestimate
                    "NIR": water_balance.net_irrigation(etc, pe) if complete else None})
    return out


def volumes(nir_mm, area_m2):
    """Irrigation volumes from a depth; per-area values need no area."""
    out = {"NIR_m3_per_da": water_balance.volume_per_decare(nir_mm),
           "NIR_m3_per_ha": water_balance.volume_per_hectare(nir_mm)}
    if area_m2 is not None:
        out["area_m2"] = area_m2
        out["NIR_m3"] = water_balance.depth_to_volume_m3(nir_mm, area_m2)
    return out


def _warnings(daily, summary, today):
    w = []
    if summary["season_end"] > today:
        w.append("Season ends on {} which is after today ({}); no climate data exists for "
                 "future days.".format(summary["season_end"], today))
    no_data = sum(d["no_data"] for d in daily)
    if no_data:
        w.append("{} season day(s) have no climate record.".format(no_data))
    gaps = summary["missing_days"] - no_data
    if gaps:
        w.append("{} season day(s) have incomplete climate data (missing ETo or rainfall).".format(gaps))
    if summary["missing_days"]:
        w.append("Totals cover only days with complete data; periods with missing days have "
                 "no net irrigation value.")
    return w
