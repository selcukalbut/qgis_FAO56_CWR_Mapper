# FAO-56 Crop Water Requirement Mapper (QGIS plugin)

Computes FAO-56 Penman-Monteith reference evapotranspiration (ETo), single crop
coefficient crop evapotranspiration (ETc = Kc × ETo), effective rainfall and net
irrigation requirement (mm, m³, m³/da, m³/ha) for polygon or point layers.

**Status:** v0.0.12 – calculation core and a QGIS Processing algorithm; no dialog yet.

## Layout

```
fao56_cwr_mapper/        QGIS plugin package (zip this folder to install)
  core/fao56.py          FAO-56 ETo, one function per equation
  core/water_balance.py  Kc curve (Eq. 66), effective rainfall, net irrigation, units
  core/eto_series.py     Daily ETo series from climate records (missing days flagged)
  core/crop_table.py     Kc table from FAO-56 Table 12 (book-checked), user CSV, overrides
  core/stage_table.py    Stage lengths from FAO-56 Table 11, Table 11/12 crop mapping
  core/field_balance.py  ETc, effective rainfall, net irrigation per day/dekad/month/season
  core/report.py         Run report (text/HTML): method, data source, results, warnings
  pipeline.py            Point chain: NASA POWER -> ETo -> ETc -> net irrigation
  qgis_processing/       Processing provider and field algorithm (QGIS network stack)
  climate_sources/       NASA POWER daily point client (with local cache)
  data/                  FAO-56 Tables 11/12 as CSV, Kc range variants, crop mapping
tests/                   Unit tests against FAO-56 worked examples (no QGIS needed)
sample_data/             Example field layer (Tekirdağ)
tools/                   Reproducible extraction of FAO-56 tables + documented corrections
docs/                    Planning draft and table review list (Turkish)
```

## Using it in QGIS

Processing Toolbox → *FAO-56 Crop Water* → *Field crop water and net irrigation
requirement*. Input: polygon (fields) or point layer. Per feature it reads the
crop name and planting date from fields (or uses the defaults), takes stage
lengths from four fields or from an FAO-56 Table 11 example matching a region
keyword (one for all features or a per-feature region field), downloads NASA POWER daily data and writes ETo, ETc, P, Pe, net
irrigation (mm, m³, m³/da, m³/ha), peak dekad, missing days and a status
message. The result layer is styled by net irrigation (mm, blue classes; grey =
no value, see `status`); in a GeoPackage the style is saved as default.
Optional outputs: daily series and dekad totals (CSV) and a run report (HTML or
text) with inputs, method, data source and attribution, per-field results,
warnings and limitations (example: `sample_data/tekirdag_report.html`).

Sample data: `sample_data/tekirdag_fields.gpkg` – four fields near Tekirdağ
(UTM 35N) with `crop`, `planted` and `region` fields (maize, sunflower, tomato,
winter wheat). Fields named `crop`, `planted` and `region` are selected
automatically (maize uses the FAO-56 Table 11 'Spain' example, the other crops
'Mediterranean'); layers without them fall back to the default values.

## Running the tests

```bash
python3 -m unittest discover -s tests -t . -v
```

The core uses only the Python standard library, so tests run with any Python ≥ 3.9.
The QGIS algorithm test is skipped there; run it with the QGIS interpreter (macOS):

```bash
PYTHONPATH=/Applications/QGIS.app/Contents/Resources/qgis/python/plugins:. /Applications/QGIS.app/Contents/MacOS/python -m unittest tests.test_qgis_algorithm -v
```

## Verified against FAO-56

| Example | Quantity | Published | Core |
|---|---|---|---|
| 2 | P, γ (z = 1800 m) | 81.8 kPa, 0.054 | ✓ |
| 3, 5 | es, ea (three RH methods) | 2.39; 1.70 / 1.69 / 1.78 kPa | ✓ |
| 8, 9 | dr, δ, ωs, Ra, N (20° S, J = 246) | 0.985, 0.120, 1.527, 32.2, 11.7 | ✓ |
| 10, 11 | Rs, Rso, Rnl, Rn (Rio de Janeiro) | 14.5, 18.8, 3.5, 7.6 | ✓ |
| 14 | u₂ from 10 m | 2.4 m/s | ✓ |
| 17 | Daily ETo, all intermediates (Brussels, 6 July) | 3.9 mm/day | 3.88 |

Cross-check: fed with Open-Meteo's own daily inputs (Tekirdağ, July 2025) the
core reproduces Open-Meteo's FAO-56 ET0 monthly total within 0.1 %.

## Data sources and attribution

Climate data: NASA POWER daily point API (no key). These data were obtained
from the NASA Langley Research Center (LaRC) POWER Project funded through the
NASA Earth Science/Applied Science Program.

POWER is a coarse global grid (about 0.5°). Near coasts or in complex terrain it
can differ markedly from local conditions; local station data is recommended
where available.

## License

GPL v2 or later – see `LICENSE` (a copy is shipped inside the plugin package).

Reference: Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998). *Crop
evapotranspiration – Guidelines for computing crop water requirements.* FAO
Irrigation and Drainage Paper 56. Rome: FAO.
