# FAO-56 Crop Water Requirement Mapper (QGIS plugin)

Computes FAO-56 Penman-Monteith reference evapotranspiration (ETo), single crop
coefficient crop evapotranspiration (ETc = Kc × ETo), effective rainfall and net
irrigation requirement (mm, m³, m³/da, m³/ha) for polygon or point layers.

**Status:** v0.2.0 – experimental; a QGIS Processing algorithm (QGIS 3.22+, QGIS 4 declared but not yet tested there) with NASA POWER, Open-Meteo or weather station climate data. No soil water balance yet (planned for v0.3).

## Layout

```
fao56_cwr_mapper/        QGIS plugin package (build the zip with tools/build_plugin.py)
  core/fao56.py          FAO-56 ETo, one function per equation
  core/water_balance.py  Kc curve (Eq. 66), effective rainfall (fixed, USDA SCS), net irrigation, units
  core/eto_series.py     Daily ETo series from climate records (missing days flagged)
  core/crop_table.py     Kc table from FAO-56 Table 12 (book-checked), user CSV, overrides
  core/stage_table.py    Stage lengths from FAO-56 Table 11, Table 11/12 crop mapping
  core/field_balance.py  ETc, effective rainfall, net irrigation per day/dekad/month/season
  core/report.py         Run report (text/HTML): method, data source, results, warnings
  pipeline.py            Point chain: climate -> ETo -> ETc -> net irrigation
  qgis_processing/       Processing provider and field algorithm (QGIS network stack)
  climate_sources/       NASA POWER and Open-Meteo clients (with local cache), station CSV reader
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

Cross-check: fed with Open-Meteo's own daily inputs (Tekirdağ, 1 May – 30 Sep
2025) the core reproduces Open-Meteo's FAO-56 ET0 season total within 0.14 %
(ERA5-Seamless: 836.4 vs 837.6 mm; Best match 0.03 %, ERA5 1.2 %).

## Effective rainfall

*Effective rainfall method*:

- **Fixed fraction** (default, 0.8): Pe = fraction × P, per day.
- **USDA SCS (CROPWAT form)** (Smith 1992, FAO Irrigation and Drainage Paper 46):
  Pe = P (125 − 0.2 P) / 125 for P ≤ 250 mm, Pe = 125 + 0.1 P above (monthly P).
- **USDA SCS (NEH Part 623)** (USDA NRCS 1993, Eq. 2-84 and 2-85, from USDA 1970):
  Pe = SF (0.70917 P^0.82416 − 0.11556) 10^(0.02426 ETc) in inches, with the soil
  water storage factor SF = 0.531747 + 0.295164 D − 0.057697 D² + 0.003804 D³;
  D is the usable soil water storage (40–60 % of the available water in the root
  zone; default 75 mm ≈ 3 in, the basis of NEH Table 2-43). Pe is limited to the
  lesser of P and ETc. Checked against the NEH worked example (P 4.7 in, ETc
  7.6 in → 3.70 in) and Table 2-43.

Both SCS forms are monthly formulas. Each dekad's rainfall (and ETc) is scaled to
its calendar month (× days in the month / days in the dekad), the formula applied
and the result scaled back – factor 3 for a 10-day dekad of a 30-day month, as in
CROPWAT's decade form – and the dekad Pe is shared among its days in proportion to
their rainfall. The method is written to `pe_method`.

## Weather station data

Choose *Climate data source = Weather stations* and give:

- **Station data (CSV)** – one row per station and day. Column names are
  recognised in English or Turkish, ignoring case, spaces and units in brackets
  (`Tmax (°C)`, `Maksimum Sıcaklık (°C)`):

  | variable | columns (any of) | unit |
  |---|---|---|
  | station (several stations) | `station`, `istasyon`, `istasyon no` | |
  | date | `date`, `tarih` (YYYY-MM-DD or DD.MM.YYYY) | |
  | Tmax, Tmin | `tmax`, `tmin`, `maksimum sicaklik`, `minimum sicaklik` | °C |
  | rainfall | `precip`, `rain`, `yagis` | mm |
  | humidity | `tdew` / `rhmax` + `rhmin` / `rhmax` / `rh`, `nem` | °C, % |
  | wind | `u2` (at 2 m) or `wind`, `ruzgar` (height as a parameter) | m/s |
  | radiation | `rs`, `radyasyon` or `sunshine`, `guneslenme` (hours) | MJ m⁻² day⁻¹, h |

  Delimiters `,` `;` or tab; with `;` a decimal comma is fine. Empty cells,
  `NA`, `-`, `-999` mean missing. UTF-8 or Windows-1254 (Turkish) encoding.
- **Station locations** – a point layer with the station ID (matching the CSV)
  and the station elevation in metres.

*Station assignment*: each field uses its nearest station within the maximum
distance (`station_km` in the result), or – for polygons – **Thiessen area
weighting**: the field is intersected with the stations' Thiessen polygons
(built in an azimuthal equidistant projection centred on the stations) and the
ellipsoidal intersection areas weight each station's daily ETo (computed at the
field's latitude with the station elevation) and rainfall. Stations farther than
the maximum distance are left out; on days a station has no data the other
weights are rescaled. The weights are written to `stn_weight`. Missing humidity, radiation or wind can be estimated with the
FAO-56 procedures for missing data – ea from Tmin (Eq. 48), Rs from the
temperature range (Hargreaves, Eq. 50, kRs 0.16 interior / 0.19 coastal) and
u2 = 2 m/s; every estimate is listed in `status` and in the run report.

## Open-Meteo (ERA5 reanalysis)

*Climate data source = Open-Meteo* downloads daily ECMWF ERA5 / ERA5-Land
reanalysis from the [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
(no key). Models: **ERA5-Seamless** (default; ERA5-Land 0.1° temperature and
humidity with ERA5 0.25° wind and radiation), **ERA5** (0.25°) and **Best match**
(also blends the ECMWF IFS 9 km model, recent days without delay). ERA5 data
arrive with about 5 days delay; those days count as missing. The plugin computes
ETo itself from Tmax, Tmin, mean dewpoint, shortwave radiation and the mean 10 m
wind (converted to 2 m, Eq. 47); elevation is the point elevation Open-Meteo
returns (90 m DEM). Fields within about 1 km (0.01°) share one download.

**Terms:** the free Open-Meteo API may only be used for non-commercial purposes
([terms](https://open-meteo.com/en/terms)); commercial users need an Open-Meteo
subscription or another source. Data are CC BY 4.0: *Weather data by
Open-Meteo.com; generated using Copernicus Climate Change Service information.*
The run report lists the attribution and the citations (Zippenfenig 2023;
Hersbach et al. 2023; Muñoz Sabater 2019).

## Comparing the climate sources

`docs/source_comparison.md` (Turkish) compares NASA POWER and Open-Meteo on the
sample fields for the 2024 seasons, with the three effective rainfall methods;
`tools/validation/compare_sources.py` reproduces it (QGIS Python). The script
can add the NOAA GSOD record of the Tekirdağ station; because GSOD data of
non-US stations fall under WMO Resolution 40, those data and results stay in
the gitignored `tools/validation/local/` and `docs/local/`.

## Building the plugin zip

```bash
python3 tools/build_plugin.py
```

Writes `dist/fao56_cwr_mapper-<version>.zip` and checks it against the PyQGIS
cookbook release rules (required metadata, LICENSE, folder name, icon, no hidden
or compiled files). To test the zip as an installed plugin in headless QGIS,
isolated from the repository code (macOS paths shown):

```bash
cd /tmp && /Applications/QGIS.app/Contents/MacOS/python /path/to/repo/tools/check_plugin_zip_qgis.py /path/to/repo/dist/fao56_cwr_mapper-0.2.0.zip
```

Before uploading, run the same security scanners as plugins.qgis.org
(Bandit and detect-secrets block a version; critical Flake8 rules are checked too):

```bash
pip install bandit detect-secrets flake8
bandit -r fao56_cwr_mapper
detect-secrets scan fao56_cwr_mapper
flake8 --select=F821,F823,F831,E901,E902,E999,F401,F841 fao56_cwr_mapper
```

## Data sources and attribution

Climate data: NASA POWER daily point API (no key). These data were obtained
from the NASA Langley Research Center (LaRC) POWER Project funded through the
NASA Earth Science/Applied Science Program.

POWER is a coarse global grid (meteorology 0.5° × 0.625°, solar radiation 1° × 1°).
Fields that fall in the same pair of grid cells share one download, so large
layers need far fewer requests (200 points across Thrace: 28 downloads).
Near coasts or in complex terrain the grid can differ markedly from local
conditions; local station data is recommended where available.

Open-Meteo: Weather data by Open-Meteo.com, CC BY 4.0; generated using
Copernicus Climate Change Service information. The free API is for
non-commercial use only (see the Open-Meteo section above).

## License

GPL v2 or later – see `LICENSE` (a copy is shipped inside the plugin package).

Reference: Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998). *Crop
evapotranspiration – Guidelines for computing crop water requirements.* FAO
Irrigation and Drainage Paper 56. Rome: FAO.
