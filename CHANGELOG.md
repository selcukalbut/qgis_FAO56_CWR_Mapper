# Changelog

## Unreleased (0.2.0)

- Weather station data: CSV with one row per station and day (English or
  Turkish column names, `,` `;` or tab, decimal comma, UTF-8 or Windows-1254)
  and a station point layer with ID and elevation. Nearest station within a
  maximum distance, or Thiessen area weighting of daily ETo and rainfall for
  polygons (weights in `stn_weight`, reweighting on days a station is missing).
- FAO-56 procedures for missing station data: ea from Tmin (Eq. 48), Rs from
  the temperature range (Eq. 50, kRs 0.16 / 0.19), u2 = 2 m/s; sunshine hours
  (Eq. 35), RHmax/RHmin (Eq. 17, 18), wind height conversion (Eq. 47).
- Open-Meteo Historical Weather API as a third climate source (ERA5-Seamless,
  ERA5 or Best match; one download per 0.01° point, local cache). The report
  states the non-commercial terms, CC BY 4.0 attribution and citations.
- Run report method, data source, references and limitations follow the
  chosen climate source.

## 0.1.1 – 2026-11-03 (experimental)

- Security scan fixes (0.1.0 was blocked on plugins.qgis.org): the plugin no
  longer contains `urllib.request.urlopen` (Bandit B310); all downloads go
  through QGIS's network stack, and the urllib fetcher for scripts moved to
  `tools/power_urllib.py`. A failed style save is logged to the QGIS message
  log instead of being ignored (Bandit B110). Bandit, detect-secrets and the
  critical Flake8 rules report no findings.
- `tools/build_plugin.py` refuses code patterns that the security scan reports.
- Qt6 / QGIS 4 readiness: Qt enums in fully scoped form, QGIS enums from the
  Qgis namespace when available (fallback to the QGIS 3.22 names), result
  fields typed with QMetaType on QGIS 3.38+; no deprecation warnings on 3.44.
- Help text states the NASA POWER grid sizes (meteorology 0.5° × 0.625°,
  radiation 1° × 1°) and that fields in the same cells share one download.

## 0.1.0 – 2026-10-27 (experimental)

First public release.

### Features

- Processing algorithm *Field crop water and net irrigation requirement* for
  polygon (fields) or point layers; batch and Graphical Modeler compatible.
- FAO-56 Penman-Monteith daily ETo from NASA POWER (no API key), actual vapour
  pressure from dewpoint (Eq. 14), RH fallback (Eq. 19).
- Single crop coefficient ETc = Kc × ETo with FAO-56 Table 12 Kc values and
  Table 11 stage lengths, both checked against the printed publication;
  documented corrections in `tools/fao56_corrections.csv`.
- Crop, planting date and region keyword per feature from fields (`crop`,
  `planted`, `region` preselected) or as defaults; stage lengths from four
  fields or chosen from Table 11 by region, then planting month.
- Effective rainfall as a fixed fraction; net irrigation requirement per dekad
  (CROPWAT-like, default) or per day; volumes in m³, m³/da, m³/ha from
  ellipsoidal areas; optional gross requirement from application efficiency.
- One NASA POWER download per grid cell (fields in the same cells share it),
  local cache, requests through the QGIS network stack (proxy settings apply).
- Result layer styled by net irrigation; optional daily and dekad CSV; HTML or
  text run report with method, data source, per-field results and warnings.
- Missing climate days are never filled; affected periods get no value and
  every feature carries a status message.

### Validation

- Unit tests against the FAO-56 worked examples (Examples 2–17).
- Same results as the Sulama Programlama web app's Penman-Monteith code to
  machine precision when the same vapour pressure method is used
  (`docs/web_app_comparison.md`, in Turkish).

### Known limitations

- NASA POWER is a coarse global grid; near coasts or in complex terrain it can
  differ markedly from local stations (around Tekirdağ summer ETo is about 15 %
  higher than ERA5-based Open-Meteo).
- No soil water balance yet: crops of the rainy season (e.g. winter cereals)
  get overestimated requirements.
- No climatic adjustment of Kc mid / Kc end (FAO-56 Eq. 62, 65).
- Tested with QGIS 3.44 only; declared minimum is 3.22.
