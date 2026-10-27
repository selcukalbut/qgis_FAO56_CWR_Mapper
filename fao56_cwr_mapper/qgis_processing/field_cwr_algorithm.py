"""Processing algorithm: FAO-56 crop water and net irrigation requirement per field."""

import csv
import difflib
from datetime import date

from qgis.core import (
    NULL,
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsFeature,
    QgsFields,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDateTime,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingUtils,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QDate, QDateTime

from .. import pipeline
from ..climate_sources import nasa_power
from ..climate_sources.nasa_power import ATTRIBUTION
from ..core import crop_table, field_balance, report, stage_table
from . import compat, network
from .styling import NirStylePostProcessor

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
NIR_PERIODS = [field_balance.NIR_DEKAD, field_balance.NIR_DAILY]

# name, kind (compat.make_field), length, precision
RESULT_FIELDS = [
    ("crop_used", "string", 80, 0),
    ("stage_used", "string", 120, 0),
    ("season_beg", "date", 0, 0),
    ("season_end", "date", 0, 0),
    ("ETo_mm", "double", 10, 1),
    ("ETc_mm", "double", 10, 1),
    ("P_mm", "double", 10, 1),
    ("Pe_mm", "double", 10, 1),
    ("NIR_mm", "double", 10, 1),
    ("NIR_m3_da", "double", 10, 1),
    ("NIR_m3_ha", "double", 10, 1),
    ("area_m2", "double", 14, 1),
    ("NIR_m3", "double", 14, 1),
    ("GIR_mm", "double", 10, 1),
    ("peak_dekad", "string", 12, 0),
    ("peak_mm", "double", 10, 1),
    ("miss_days", "int", 6, 0),
    ("nir_period", "string", 8, 0),
    ("pe_frac", "double", 5, 2),
    ("elev_m", "double", 8, 1),
    ("clim_src", "string", 80, 0),
    ("status", "string", 1000, 0),   # shapefile output truncates to 254
]
DAILY_COLUMNS = ["fid", "date", "dekad", "stage", "Kc", "ETo", "ETc", "P", "Pe", "NIR"]
PERIOD_COLUMNS = ["fid", "period", "days", "missing_days", "ETo", "ETc", "P", "Pe", "NIR"]


def _round(v, n=1):
    return NULL if v is None else round(v, n)


def _to_date(value):
    """Python date from a QDate/QDateTime/'YYYY-MM-DD' attribute, or None."""
    if value is None or value == NULL:
        return None
    if isinstance(value, QDateTime):
        value = value.date()
    if isinstance(value, QDate):
        return date(value.year(), value.month(), value.day()) if value.isValid() else None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        raise ValueError("planting date '{}' is not YYYY-MM-DD".format(text))


class FieldCropWaterRequirement(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    CROP_FIELD = "CROP_FIELD"
    CROP = "CROP"
    PLANTING_FIELD = "PLANTING_FIELD"
    PLANTING_DATE = "PLANTING_DATE"
    STAGE_REGION = "STAGE_REGION"
    REGION_FIELD = "REGION_FIELD"
    L_FIELDS = ("L_INI_FIELD", "L_DEV_FIELD", "L_MID_FIELD", "L_LATE_FIELD")
    USER_KC_CSV = "USER_KC_CSV"
    PE_FRACTION = "PE_FRACTION"
    NIR_PERIOD = "NIR_PERIOD"
    EFFICIENCY = "EFFICIENCY"
    USE_CACHE = "USE_CACHE"
    OUTPUT = "OUTPUT"
    OUTPUT_DAILY = "OUTPUT_DAILY"
    OUTPUT_DEKAD = "OUTPUT_DEKAD"
    OUTPUT_REPORT = "OUTPUT_REPORT"

    # replaced in tests to run without network
    fetcher = staticmethod(network.qgis_fetcher)

    def __init__(self):
        super().__init__()
        self._crops = crop_table.load_kc_table()

    def createInstance(self):
        return FieldCropWaterRequirement()

    def name(self):
        return "fieldcropwaterrequirement"

    def displayName(self):
        return "Field crop water and net irrigation requirement"

    def group(self):
        return "Crop water requirement"

    def groupId(self):
        return "cropwater"

    def shortHelpString(self):
        return (
            "Computes FAO-56 crop water requirement for each field (polygon) or point: "
            "daily Penman-Monteith ETo from NASA POWER, single crop coefficient ETc = Kc x ETo, "
            "effective rainfall Pe as a fixed fraction of rainfall and net irrigation "
            "requirement NIR = max(0, ETc - Pe) per dekad (CROPWAT-like, default) or per day.\n\n"
            "Crop: a text field with the crop name exactly as listed in the Crop parameter "
            "(FAO-56 Table 12, e.g. 'Tomato', 'Sunflower - irrigated'), or the Crop parameter "
            "for all features. Planting date: a date field (or YYYY-MM-DD text) or the "
            "Planting date parameter.\n\n"
            "Stage lengths: four optional numeric fields (days), otherwise an FAO-56 Table 11 "
            "example whose region matches the Region keyword (or, per feature, the value of "
            "the Region keyword field, e.g. 'Spain' for maize). If no region matches, the "
            "example planted in the same month is used and 'status' carries a warning that "
            "names the choice and the other examples for that month. The option used is "
            "written to 'stage_used'; local stage lengths are always preferable.\n\n"
            "Climate is queried at a point inside each polygon. NASA POWER is a coarse global "
            "grid (meteorology 0.5 x 0.625 degree, solar radiation 1 x 1 degree); fields in the "
            "same cells share one download. Compare with local station data where possible. "
            "Areas are ellipsoidal. Days without data are never filled; they are counted in "
            "'miss_days' and periods with gaps get no net irrigation value.\n\n" + ATTRIBUTION)

    def initAlgorithm(self, config=None):
        names = [c.name for c in self._crops]
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, "Fields (polygons) or points",
            [compat.SOURCE_POLYGON, compat.SOURCE_POINT]))
        self.addParameter(QgsProcessingParameterField(
            self.CROP_FIELD, "Crop name field (optional)", parentLayerParameterName=self.INPUT,
            type=compat.FIELD_STRING, optional=True, defaultValue="crop"))
        self.addParameter(QgsProcessingParameterEnum(
            self.CROP, "Crop (used when no crop field is given or it is empty)", options=names,
            defaultValue=names.index("Tomato")))
        self.addParameter(QgsProcessingParameterField(
            self.PLANTING_FIELD, "Planting date field (optional; date or YYYY-MM-DD text)",
            parentLayerParameterName=self.INPUT, type=compat.FIELD_ANY,
            optional=True, defaultValue="planted"))
        last_year = date.today().year - 1
        self.addParameter(QgsProcessingParameterDateTime(
            self.PLANTING_DATE, "Planting date (used when no planting date field is given)",
            type=compat.DATETIME_DATE, defaultValue=QDate(last_year, 4, 15)))
        self.addParameter(QgsProcessingParameterString(
            self.STAGE_REGION, "Region keyword for FAO-56 Table 11 stage lengths",
            defaultValue="Mediterranean", optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.REGION_FIELD, "Region keyword field (optional, overrides the keyword per feature)",
            parentLayerParameterName=self.INPUT, type=compat.FIELD_STRING,
            optional=True, defaultValue="region"))
        for key, label in zip(self.L_FIELDS, ("initial", "development", "mid-season", "late season")):
            p = QgsProcessingParameterField(
                key, "Stage length field, {} [days] (optional)".format(label),
                parentLayerParameterName=self.INPUT, type=compat.FIELD_NUMERIC,
                optional=True)
            p.setFlags(p.flags() | compat.FLAG_ADVANCED)
            self.addParameter(p)
        p = QgsProcessingParameterFile(
            self.USER_KC_CSV, "User crop coefficient table (CSV: crop, variant, kc_ini, kc_mid, kc_end)",
            extension="csv", optional=True)
        p.setFlags(p.flags() | compat.FLAG_ADVANCED)
        self.addParameter(p)
        self.addParameter(QgsProcessingParameterNumber(
            self.PE_FRACTION, "Effective rainfall fraction (Pe = fraction x P)",
            type=compat.NUMBER_DOUBLE, minValue=0.0, maxValue=1.0, defaultValue=0.8))
        self.addParameter(QgsProcessingParameterEnum(
            self.NIR_PERIOD, "Net irrigation evaluated per",
            options=["Dekad (CROPWAT-like)", "Day"], defaultValue=0))
        p = QgsProcessingParameterNumber(
            self.EFFICIENCY, "Irrigation application efficiency for gross requirement (0 = not computed)",
            type=compat.NUMBER_DOUBLE, minValue=0.0, maxValue=1.0, defaultValue=0.0)
        p.setFlags(p.flags() | compat.FLAG_ADVANCED)
        self.addParameter(p)
        p = QgsProcessingParameterBoolean(self.USE_CACHE, "Use local cache for climate downloads",
                                          defaultValue=True)
        p.setFlags(p.flags() | compat.FLAG_ADVANCED)
        self.addParameter(p)
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, "Crop water requirement"))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_DAILY, "Daily time series (CSV)", fileFilter="CSV files (*.csv)",
            optional=True, createByDefault=False))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_DEKAD, "Dekad totals (CSV)", fileFilter="CSV files (*.csv)",
            optional=True, createByDefault=False))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_REPORT, "Run report (method, data source, results, warnings)",
            fileFilter="HTML files (*.html);;Text files (*.txt)", optional=True,
            createByDefault=False))

    # --- helpers ------------------------------------------------------------

    def _find_crop(self, crops, name):
        try:
            return crop_table.find_crop(crops, name)
        except KeyError:
            close = difflib.get_close_matches(name, [c.name for c in crops], n=3, cutoff=0.5)
            hint = " Did you mean: {}?".format(", ".join(close)) if close else ""
            raise ValueError("crop '{}' not found in the crop table.{}".format(name, hint))

    def _stage(self, feature, l_fields, crop, stages, mapping, region, planting_date):
        """(StageLengths, note); note explains a fallback choice, else None."""
        if all(l_fields):
            values = [feature[f] for f in l_fields]
            if any(v is None or v == NULL for v in values):
                raise ValueError("stage length fields are empty")
            lengths = [int(round(float(v))) for v in values]
            if min(lengths) < 0 or sum(lengths) == 0:
                raise ValueError("invalid stage lengths {}".format(lengths))
            return stage_table.StageLengths(crop.crop, crop.variant, 0, *lengths, total_printed=None,
                                            region="field attributes", source="field attributes"), None
        options = stage_table.stage_options(crop, stages, mapping)
        if not options:
            raise ValueError("FAO-56 Table 11 has no stage lengths for '{}'; provide the four "
                             "stage length fields".format(crop.name))
        return stage_table.select_stage_option(options, region, planting_date)

    def _check_planting_field(self, source, name):
        """Stop early when the planting date field clearly holds no dates."""
        values = []
        for feat in source.getFeatures():
            v = feat[name]
            if v is not None and v != NULL and str(v).strip():
                values.append(v)
            if len(values) >= 20:
                break
        if not values:
            return
        for v in values:
            try:
                if _to_date(v):
                    return
            except ValueError:
                pass
        raise QgsProcessingException(
            "Planting date field '{}' contains no dates (e.g. '{}'). Choose the field with "
            "planting dates or leave it empty to use the Planting date parameter.".format(name, values[0]))

    # --- run ----------------------------------------------------------------

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))

        crops = list(self._crops)
        user_csv = self.parameterAsFile(parameters, self.USER_KC_CSV, context)
        if user_csv:
            user = crop_table.load_user_kc_csv(user_csv)
            user_names = {c.name.lower() for c in user}
            crops = user + [c for c in crops if c.name.lower() not in user_names]
            feedback.pushInfo("Loaded {} crop(s) from {}".format(len(user), user_csv))
        stages = stage_table.load_stage_table()
        mapping = stage_table.load_crop_mapping()

        def layer_field(key):
            # defaults name the fields 'crop', 'planted', 'region'; a layer without them just
            # uses the default values instead of failing on every feature
            name = self.parameterAsString(parameters, key, context)
            if name and source.fields().indexOf(name) < 0:
                feedback.pushInfo("Field '{}' not found in the input layer; not used.".format(name))
                return ""
            return name

        crop_field = layer_field(self.CROP_FIELD)
        default_crop = self._crops[self.parameterAsEnum(parameters, self.CROP, context)]
        plant_field = layer_field(self.PLANTING_FIELD)
        if plant_field:
            self._check_planting_field(source, plant_field)
        qd = self.parameterAsDateTime(parameters, self.PLANTING_DATE, context).date()
        default_plant = date(qd.year(), qd.month(), qd.day())
        region = (self.parameterAsString(parameters, self.STAGE_REGION, context).strip(),
                  layer_field(self.REGION_FIELD))
        l_fields = [self.parameterAsString(parameters, k, context) for k in self.L_FIELDS]
        if any(l_fields) and not all(l_fields):
            raise QgsProcessingException("Give all four stage length fields or none.")
        pe_fraction = self.parameterAsDouble(parameters, self.PE_FRACTION, context)
        nir_period = NIR_PERIODS[self.parameterAsEnum(parameters, self.NIR_PERIOD, context)]
        efficiency = self.parameterAsDouble(parameters, self.EFFICIENCY, context) or None
        cache = network.cache_dir() if self.parameterAsBoolean(parameters, self.USE_CACHE, context) else None

        fields = QgsFields()
        for name, kind, length, prec in RESULT_FIELDS:
            fields.append(compat.make_field(name, kind, length, prec))
        out_fields = QgsProcessingUtils.combineFields(source.fields(), fields)
        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, out_fields,
                                             source.wkbType(), source.sourceCrs())
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        to_wgs84 = QgsCoordinateTransform(source.sourceCrs(), WGS84, context.transformContext())
        da = QgsDistanceArea()
        da.setSourceCrs(source.sourceCrs(), context.transformContext())
        da.setEllipsoid(context.ellipsoid() or "EPSG:7030")
        is_polygon = QgsWkbTypes.geometryType(source.wkbType()) == compat.GEOMETRY_POLYGON

        label_field = "name" if source.fields().indexOf("name") >= 0 else None

        # 1. read every feature: crop, dates, stage lengths, location, area (no network)
        records = []
        for feat in source.getFeatures():
            if feedback.isCanceled():
                break
            label = feat[label_field] if label_field else None
            rec = {"id": feat.id(), "attrs": feat.attributes(), "geometry": feat.geometry(),
                   "label": str(label) if label not in (None, NULL) else "fid {}".format(feat.id()),
                   "prep": None, "error": None}
            try:
                rec["prep"] = self._prepare_feature(
                    feat, crops, default_crop, crop_field, plant_field, default_plant, l_fields,
                    stages, mapping, region, to_wgs84, da, is_polygon)
            except Exception as exc:  # one bad field must not stop the run
                rec["error"] = str(exc)    # a message only: stored exceptions would keep frames alive
            records.append(rec)

        # 2. one NASA POWER download per grid cell, covering all seasons in that cell
        today = date.today()
        groups = {}
        for rec in records:
            prep = rec["prep"]
            if prep is None or prep["start"] > today:
                continue                     # errors and future seasons are reported in step 3
            g = groups.setdefault(prep["cell"], {"lat": prep["lat"], "lon": prep["lon"],
                                                 "start": prep["start"], "end": prep["end"]})
            g["start"], g["end"] = min(g["start"], prep["start"]), max(g["end"], prep["end"])
        feedback.pushInfo("{} feature(s) in {} NASA POWER grid cell(s): {} download(s).".format(
            len(records), len(groups), len(groups)))
        series, cell_errors = {}, {}
        for n, (key, g) in enumerate(groups.items()):
            if feedback.isCanceled():
                break
            try:
                series[key] = nasa_power.fetch(g["lat"], g["lon"], g["start"], min(g["end"], today),
                                               fetcher=self.fetcher, cache_dir=cache, today=today)
            except Exception as exc:
                cell_errors[key] = str(exc)
            feedback.setProgress(80.0 * (n + 1) / len(groups))

        # 3. compute and write every feature in input order
        daily_rows, dekad_rows, report_rows, failures = [], [], [], 0
        total = len(records) or 1
        for i, rec in enumerate(records):
            if feedback.isCanceled():
                break
            prep = rec["prep"]
            error = rec["error"] or (cell_errors.get(prep["cell"]) if prep else None)
            if error is None:
                try:
                    result = self._compute_feature(prep, series.get(prep["cell"]), pe_fraction,
                                                   nir_period, efficiency, cache, today)
                except Exception as exc:  # one bad field must not stop the run
                    error = str(exc)
            if error is not None:
                failures += 1
                result = {"status": "error: {}".format(error)}
                feedback.reportError("Feature {}: {}".format(rec["id"], error), fatalError=False)
            out = QgsFeature(out_fields)
            out.setGeometry(rec["geometry"])
            attrs = rec["attrs"]
            out.setAttributes(attrs + [result.get(name, NULL) for name, _, _, _ in RESULT_FIELDS])
            sink.addFeature(out, compat.FAST_INSERT)
            for d in result.get("_daily", []):
                daily_rows.append([rec["id"], d["day"].isoformat(), d["dekad"], d["stage"],
                                   round(d["Kc"], 3)] + [_csv(d[k]) for k in ("ETo", "ETc", "P", "Pe", "NIR")])
            for p in result.get("_dekad", []):
                dekad_rows.append([rec["id"]] + [_csv(p[k]) for k in PERIOD_COLUMNS[1:]])
            report_rows.append(_report_row(rec["label"], result))
            feedback.setProgress(80.0 + 20.0 * (i + 1) / total)

        if context.willLoadLayerOnCompletion(dest_id):
            context.layerToLoadOnCompletionDetails(dest_id).setPostProcessor(
                NirStylePostProcessor.create())
        outputs = {self.OUTPUT: dest_id}
        for key, columns, rows in ((self.OUTPUT_DAILY, DAILY_COLUMNS, daily_rows),
                                   (self.OUTPUT_DEKAD, PERIOD_COLUMNS, dekad_rows)):
            path = self.parameterAsFileOutput(parameters, key, context)
            if path:
                with open(path, "w", newline="", encoding="utf-8") as fh:
                    w = csv.writer(fh)
                    w.writerow(columns)
                    w.writerows(rows)
                outputs[key] = path
        path = self.parameterAsFileOutput(parameters, self.OUTPUT_REPORT, context)
        if path:
            meta = {"layer": source.sourceName(), "crs": source.sourceCrs().authid(),
                    "ellipsoid": da.ellipsoid(), "qgis_version": Qgis.version()}
            settings = {
                "pe_fraction": pe_fraction, "nir_period": nir_period, "efficiency": efficiency,
                "user_kc_csv": user_csv,
                "crop_source": ("field '{}' (empty values: {})".format(crop_field, default_crop.name)
                                if crop_field else "{} for all features".format(default_crop.name)),
                "planting_source": ("field '{}' (empty values: {})".format(plant_field, default_plant)
                                    if plant_field else "{} for all features".format(default_plant)),
                "stage_source": ("fields " + ", ".join(l_fields) if all(l_fields) else
                                 "FAO-56 Table 11, region keyword '{}'{}".format(
                                     region[0], ", per-feature field '{}'".format(region[1])
                                     if region[1] else "")),
            }
            outputs[self.OUTPUT_REPORT] = report.write_report(path, meta, settings, report_rows)
        if failures:
            feedback.pushWarning("{} feature(s) failed; see the 'status' field.".format(failures))
        return outputs

    def _prepare_feature(self, feat, crops, default_crop, crop_field, plant_field, default_plant,
                         l_fields, stages, mapping, region, to_wgs84, da, is_polygon):
        """Everything needed for one feature except climate data."""
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            raise ValueError("empty geometry")
        crop = default_crop
        if crop_field:
            name = feat[crop_field]
            if name not in (None, NULL) and str(name).strip():
                crop = self._find_crop(crops, str(name))
        plant = (_to_date(feat[plant_field]) if plant_field else None) or default_plant
        keyword, region_field = region
        if region_field:
            value = feat[region_field]
            if value not in (None, NULL) and str(value).strip():
                keyword = str(value).strip()
        stage, stage_note = self._stage(feat, l_fields, crop, stages, mapping, keyword, plant)

        point = geom.pointOnSurface() if is_polygon else geom.centroid()
        point.transform(to_wgs84)
        p = point.asPoint()
        area = None
        if is_polygon:
            area = da.convertAreaMeasurement(da.measureArea(geom), compat.AREA_SQUARE_METERS)
        start, end = field_balance.season_dates(plant, stage)
        return {"crop": crop, "stage": stage, "stage_note": stage_note, "plant": plant,
                "start": start, "end": end, "lat": p.y(), "lon": p.x(), "area": area,
                "cell": nasa_power.cell_key(p.y(), p.x())}

    def _compute_feature(self, prep, series, pe_fraction, nir_period, efficiency, cache, today):
        """Field balance with the climate series of the feature's grid cell."""
        crop, stage, stage_note = prep["crop"], prep["stage"], prep["stage_note"]
        r = pipeline.run_field(prep["lat"], prep["lon"], crop, stage, prep["plant"],
                               area_m2=prep["area"], pe_fraction=pe_fraction,
                               nir_period=nir_period, efficiency=efficiency, fetcher=self.fetcher,
                               cache_dir=cache, today=today, series=series)
        s = r["summary"]
        warnings = ([stage_note + "."] if stage_note else []) + s["warnings"]
        status = "ok" if not warnings else "warning: " + " ".join(warnings)
        return {
            "crop_used": crop.name, "stage_used": stage.label,
            "season_beg": QDate(s["season_start"].year, s["season_start"].month, s["season_start"].day),
            "season_end": QDate(s["season_end"].year, s["season_end"].month, s["season_end"].day),
            "ETo_mm": _round(s["ETo_mm"]), "ETc_mm": _round(s["ETc_mm"]),
            "P_mm": _round(s["P_mm"]), "Pe_mm": _round(s["Pe_mm"]),
            "NIR_mm": _round(s["NIR_mm"]), "NIR_m3_da": _round(s["NIR_m3_per_da"]),
            "NIR_m3_ha": _round(s["NIR_m3_per_ha"]),
            "area_m2": _round(s.get("area_m2")), "NIR_m3": _round(s.get("NIR_m3")),
            "GIR_mm": _round(s.get("GIR_mm")),
            "peak_dekad": s["peak_dekad"] or NULL, "peak_mm": _round(s["peak_dekad_NIR_mm"]),
            "miss_days": s["missing_days"], "nir_period": s["nir_period"],
            "pe_frac": pe_fraction, "elev_m": _round(s["elevation_m"]),
            "clim_src": s["climate_source"], "status": status[:1000],
            "_daily": r["daily"], "_dekad": r["dekad"], "_summary": s,
        }


def _report_row(label, result):
    s = result.get("_summary")
    row = {"feature": label, "status": result.get("status", "error")}
    if s:
        row.update({"crop": s["crop"], "stage": s["stage_option"],
                    "stage_example": s.get("stage_example"), "stage_lengths": s.get("stage_lengths"),
                    "climate_sources": s.get("climate_sources"),
                    "api_version": s.get("climate_api_version"),
                    "season_start": s["season_start"], "season_end": s["season_end"],
                    "ETo": s["ETo_mm"], "ETc": s["ETc_mm"], "P": s["P_mm"], "Pe": s["Pe_mm"],
                    "NIR": s["NIR_mm"], "NIR_m3": s.get("NIR_m3"), "area_m2": s.get("area_m2")})
    return row


def _csv(v):
    return "" if v is None else round(v, 3) if isinstance(v, float) else v
