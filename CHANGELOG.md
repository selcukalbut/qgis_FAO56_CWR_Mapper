# Changelog

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
