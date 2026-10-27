"""Compare the plugin with the Sulama Programlama web app for the same cases.

Usage: python3 tools/validation/compare_web_app.py web.json result.json [cache_dir]
web.json comes from run_web_app.js. The plugin is run with the web app's own Kc
and stage lengths, and the differences are split into their causes.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from fao56_cwr_mapper.climate_sources import nasa_power as np_
from fao56_cwr_mapper.core import fao56, eto_series, field_balance as fb, water_balance as wb
from fao56_cwr_mapper.core.crop_table import CropKc
from fao56_cwr_mapper.core.stage_table import StageLengths

web = json.load(open(sys.argv[1]))
out_path = sys.argv[2]
cache = sys.argv[3] if len(sys.argv) > 3 else None
LAT, LON = 40.98, 27.51
out = {}
for name, w in web.items():
    c = w["crop"]
    crop = CropKc("web", name, "", c["kcIni"], c["kcMid"], c["kcEnd"])
    stage = StageLengths(name, "", 0, c["Lini"], c["Ldev"], c["Lmid"], c["Llate"], None, region="web app")
    plant = datetime.strptime(w["rows"][0]["date"], "%Y%m%d").date()
    start, end = fb.season_dates(plant, stage)
    s = np_.fetch(LAT, LON, start, end, cache_dir=cache)
    z = s.elevation
    days = {d.day: d for d in s.days}
    # plugin as shipped: ea from dewpoint, dekad NIR, Pe = 0.8 P
    plug = fb.field_water_balance(eto_series.daily_eto_series(s.days, LAT, z), crop, stage, plant)["summary"]
    plug_daily = fb.field_water_balance(eto_series.daily_eto_series(s.days, LAT, z), crop, stage, plant,
                                        nir_period=fb.NIR_DAILY)["summary"]
    # day-by-day ETo
    d_dew, d_rh, kc_shift = [], [], []
    eto_rh_sum = etc_rh_webkc = etc_rh_plugkc = 0.0
    for i, r in enumerate(w["rows"]):
        day = datetime.strptime(r["date"], "%Y%m%d").date()
        x = days[day]
        e_dew = fao56.daily_eto(day, LAT, z, x.tmax, x.tmin, x.u2, fao56.actual_vapour_pressure_from_tdew(x.tdew), x.rs)["ETo"]
        e_rh = fao56.daily_eto(day, LAT, z, x.tmax, x.tmin, x.u2, fao56.actual_vapour_pressure_from_rhmean(x.tmax, x.tmin, x.rh), x.rs)["ETo"]
        d_dew.append(e_dew - r["eto"]); d_rh.append(e_rh - r["eto"])
        kc_plug, _ = wb.kc_for_day(i + 1, crop.kc_ini, crop.kc_mid, crop.kc_end, *stage.lengths)
        eto_rh_sum += e_rh; etc_rh_webkc += r["kc"] * e_rh; etc_rh_plugkc += kc_plug * e_rh
    P = w["sumRain"]
    scs = P * (125 - 0.2 * P) / 125 if P <= 250 else 0.1 * P + 125
    out[name] = dict(
        crop=c, plant=str(plant), end=str(end), n=len(w["rows"]), web=dict(ETo=w["sumEto"], ETc=w["sumEtc"], P=P, Pe=w["effRain"], NIR=w["netReq"]),
        plug=dict(ETo=plug["ETo_mm"], ETc=plug["ETc_mm"], P=plug["P_mm"], Pe=plug["Pe_mm"], NIR=plug["NIR_mm"], NIR_daily=plug_daily["NIR_mm"]),
        eto_rh_sum=eto_rh_sum, etc_rh_webkc=etc_rh_webkc, etc_rh_plugkc=etc_rh_plugkc,
        max_abs_diff_rh=max(abs(v) for v in d_rh), mean_diff_dew=sum(d_dew) / len(d_dew),
        max_abs_diff_dew=max(abs(v) for v in d_dew), scs_total=scs,
        plug_nir_with_web_pe=max(0.0, plug["ETc_mm"] - scs), elevation=z, sources=s.sources, api=s.api_version)
json.dump(out, open(out_path, "w"), indent=1, default=str)
for k, v in out.items():
    print("==", k, v["plant"], "->", v["end"], v["n"], "days, elev", v["elevation"], v["sources"], v["api"])
    print(" web     ", {a: round(b, 1) for a, b in v["web"].items()})
    print(" plugin  ", {a: round(b, 1) for a, b in v["plug"].items()})
    print(" ETo plugin(RH, Eq19) sum %.1f; max |daily diff| vs web %.2e mm" % (v["eto_rh_sum"], v["max_abs_diff_rh"]))
    print(" ETo plugin(Tdew, Eq14): mean daily diff %+.3f, max %.3f mm" % (v["mean_diff_dew"], v["max_abs_diff_dew"]))
    print(" ETc on RH-ETo: web Kc %.1f, plugin Kc %.1f (day offset effect %+.1f)" % (v["etc_rh_webkc"], v["etc_rh_plugkc"], v["etc_rh_plugkc"] - v["etc_rh_webkc"]))
    print(" SCS on season total %.1f; plugin ETc - SCS %.1f" % (v["scs_total"], v["plug_nir_with_web_pe"]))
