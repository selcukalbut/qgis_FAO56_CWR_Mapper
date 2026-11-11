"""Thiessen (area) weighting of station results for one field.

Each station's daily ETo is computed at the field's latitude with the station's
own elevation; the field's daily ETo and rainfall are the weighted means of the
stations that have a value on that day. When a station has no value, the
weights of the others are rescaled to sum to 1 and the day is counted as
"reweighted". A day with no station value at all is missing.
"""


def normalise_weights(weights):
    """[(station id, weight)] scaled to sum to 1, zero and negative weights dropped."""
    kept = [(sid, float(w)) for sid, w in weights if w > 0]
    total = sum(w for _, w in kept)
    if total <= 0:
        raise ValueError("no positive station weight")
    return [(sid, w / total) for sid, w in kept]


def _weighted(values):
    """Weighted mean of [(weight, value)] over the values present, and the weight used."""
    present = [(w, v) for w, v in values if v is not None]
    used = sum(w for w, _ in present)
    if used <= 0:
        return None, 0.0
    return sum(w * v for w, v in present) / used, used


def combine_eto_rows(station_rows, tolerance=1e-9):
    """Merge per-station eto_series rows into one daily series for the field.

    station_rows: [(weight, rows)] with weights summing to 1 and rows from
    eto_series.daily_eto_series. Returns rows with day, ETo, precip, missing,
    estimated (union of the stations used), reweighted (bool) and stations
    (number of stations with an ETo value that day).
    """
    by_day = {}
    for w, rows in station_rows:
        for r in rows:
            by_day.setdefault(r["day"], []).append((w, r))
    out = []
    for day in sorted(by_day):
        entries = by_day[day]
        eto, w_eto = _weighted([(w, None if r["missing"] else r["ETo"]) for w, r in entries])
        precip, w_p = _weighted([(w, r["precip"]) for w, r in entries])
        estimated = sorted({e for w, r in entries if not r["missing"] for e in r.get("estimated", [])})
        out.append({
            "day": day, "ETo": eto, "precip": precip, "missing": eto is None,
            "estimated": estimated,
            "reweighted": (eto is not None and w_eto < 1 - tolerance)
            or (precip is not None and w_p < 1 - tolerance),
            "stations": sum(1 for _, r in entries if not r["missing"]),
        })
    return out
