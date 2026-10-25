"""Processing algorithm: FAO-56 crop water and net irrigation requirement per field."""

import csv
import difflib
from datetime import date

from qgis.core import (
    NULL,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessing,
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
    QgsUnitTypes,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QDate, QDateTime, QVariant

from .. import pipeline
from ..climate_sources.nasa_power import ATTRIBUTION
from ..core import crop_table, field_balance, stage_table
from . import network
from .styling import NirStylePostProcessor

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
NIR_PERIODS = [field_balance.NIR_DEKAD, field_balance.NIR_DAILY]

# name, type, length, precision
RESULT_FIELDS = [
    ("crop_used", QVariant.String, 80, 0),
    ("stage_used", QVariant.String, 120, 0),
    ("season_beg", QVariant.Date, 0, 0),
    ("season_end", QVariant.Date, 0, 0),
    ("ETo_mm", QVariant.Double, 10, 1),
    ("ETc_mm", QVariant.Double, 10, 1),
    ("P_mm", QVariant.Double, 10, 1),
    ("Pe_mm", QVariant.Double, 10, 1),
    ("NIR_mm", QVariant.Double, 10, 1),
    ("NIR_m3_da", QVariant.Double, 10, 1),
    ("NIR_m3_ha", QVariant.Double, 10, 1),
    ("area_m2", QVariant.Double, 14, 1),
    ("NIR_m3", QVariant.Double, 14, 1),
    ("GIR_mm", QVariant.Double, 10, 1),
    ("peak_dekad", QVariant.String, 12, 0),
    ("peak_mm", QVariant.Double, 10, 1),
    ("miss_days", QVariant.Int, 6, 0),
    ("nir_period", QVariant.String, 8, 0),
    ("pe_frac", QVariant.Double, 5, 2),
    ("elev_m", QVariant.Double, 8, 1),
    ("clim_src", QVariant.String, 80, 0),
    ("status", QVariant.String, 1000, 0),   # shapefile output truncates to 254
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
    L_FIELDS = ("L_INI_FIELD", "L_DEV_FIELD", "L_MID_FIELD", "L_LATE_FIELD")
    USER_KC_CSV = "USER_KC_CSV"
    PE_FRACTION = "PE_FRACTION"
    NIR_PERIOD = "NIR_PERIOD"
    EFFICIENCY = "EFFICIENCY"
    USE_CACHE = "USE_CACHE"
    OUTPUT = "OUTPUT"
    OUTPUT_DAILY = "OUTPUT_DAILY"
    OUTPUT_DEKAD = "OUTPUT_DEKAD"

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
            "example whose region matches the Region keyword. If no region matches, the "
            "example planted in the same month is used and 'status' carries a warning that "
            "names the choice and the other examples for that month. The option used is "
            "written to 'stage_used'; local stage lengths are always preferable.\n\n"
            "Climate is queried at a point inside each polygon. NASA POWER is a coarse "
            "(about 0.5 degree) global grid; compare with local station data where possible. "
            "Areas are ellipsoidal. Days without data are never filled; they are counted in "
            "'miss_days' and periods with gaps get no net irrigation value.\n\n" + ATTRIBUTION)

    def initAlgorithm(self, config=None):
        names = [c.name for c in self._crops]
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, "Fields (polygons) or points",
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            self.CROP_FIELD, "Crop name field (optional)", parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.String, optional=True))
        self.addParameter(QgsProcessingParameterEnum(
            self.CROP, "Crop (used when no crop field is given or it is empty)", options=names,
            defaultValue=names.index("Tomato")))
        self.addParameter(QgsProcessingParameterField(
            self.PLANTING_FIELD, "Planting date field (optional)", parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Any, optional=True))
        last_year = date.today().year - 1
        self.addParameter(QgsProcessingParameterDateTime(
            self.PLANTING_DATE, "Planting date (used when no planting date field is given)",
            type=QgsProcessingParameterDateTime.Date, defaultValue=QDate(last_year, 4, 15)))
        self.addParameter(QgsProcessingParameterString(
            self.STAGE_REGION, "Region keyword for FAO-56 Table 11 stage lengths",
            defaultValue="Mediterranean", optional=True))
        for key, label in zip(self.L_FIELDS, ("initial", "development", "mid-season", "late season")):
            p = QgsProcessingParameterField(
                key, "Stage length field, {} [days] (optional)".format(label),
                parentLayerParameterName=self.INPUT, type=QgsProcessingParameterField.Numeric,
                optional=True)
            p.setFlags(p.flags() | p.FlagAdvanced)
            self.addParameter(p)
        p = QgsProcessingParameterFile(
            self.USER_KC_CSV, "User crop coefficient table (CSV: crop, variant, kc_ini, kc_mid, kc_end)",
            extension="csv", optional=True)
        p.setFlags(p.flags() | p.FlagAdvanced)
        self.addParameter(p)
        self.addParameter(QgsProcessingParameterNumber(
            self.PE_FRACTION, "Effective rainfall fraction (Pe = fraction x P)",
            type=QgsProcessingParameterNumber.Double, minValue=0.0, maxValue=1.0, defaultValue=0.8))
        self.addParameter(QgsProcessingParameterEnum(
            self.NIR_PERIOD, "Net irrigation evaluated per",
            options=["Dekad (CROPWAT-like)", "Day"], defaultValue=0))
        p = QgsProcessingParameterNumber(
            self.EFFICIENCY, "Irrigation application efficiency for gross requirement (0 = not computed)",
            type=QgsProcessingParameterNumber.Double, minValue=0.0, maxValue=1.0, defaultValue=0.0)
        p.setFlags(p.flags() | p.FlagAdvanced)
        self.addParameter(p)
        p = QgsProcessingParameterBoolean(self.USE_CACHE, "Use local cache for climate downloads",
                                          defaultValue=True)
        p.setFlags(p.flags() | p.FlagAdvanced)
        self.addParameter(p)
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, "Crop water requirement"))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_DAILY, "Daily time series (CSV)", fileFilter="CSV files (*.csv)",
            optional=True, createByDefault=False))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_DEKAD, "Dekad totals (CSV)", fileFilter="CSV files (*.csv)",
            optional=True, createByDefault=False))

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

        crop_field = self.parameterAsString(parameters, self.CROP_FIELD, context)
        default_crop = self._crops[self.parameterAsEnum(parameters, self.CROP, context)]
        plant_field = self.parameterAsString(parameters, self.PLANTING_FIELD, context)
        qd = self.parameterAsDateTime(parameters, self.PLANTING_DATE, context).date()
        default_plant = date(qd.year(), qd.month(), qd.day())
        region = self.parameterAsString(parameters, self.STAGE_REGION, context).strip()
        l_fields = [self.parameterAsString(parameters, k, context) for k in self.L_FIELDS]
        if any(l_fields) and not all(l_fields):
            raise QgsProcessingException("Give all four stage length fields or none.")
        pe_fraction = self.parameterAsDouble(parameters, self.PE_FRACTION, context)
        nir_period = NIR_PERIODS[self.parameterAsEnum(parameters, self.NIR_PERIOD, context)]
        efficiency = self.parameterAsDouble(parameters, self.EFFICIENCY, context) or None
        cache = network.cache_dir() if self.parameterAsBoolean(parameters, self.USE_CACHE, context) else None

        fields = QgsFields()
        for name, vtype, length, prec in RESULT_FIELDS:
            fields.append(QgsField(name, vtype, len=length, prec=prec))
        out_fields = QgsProcessingUtils.combineFields(source.fields(), fields)
        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, out_fields,
                                             source.wkbType(), source.sourceCrs())
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        to_wgs84 = QgsCoordinateTransform(source.sourceCrs(), WGS84, context.transformContext())
        da = QgsDistanceArea()
        da.setSourceCrs(source.sourceCrs(), context.transformContext())
        da.setEllipsoid(context.ellipsoid() or "EPSG:7030")
        is_polygon = QgsWkbTypes.geometryType(source.wkbType()) == QgsWkbTypes.PolygonGeometry

        daily_rows, dekad_rows, failures = [], [], 0
        total = source.featureCount() or 1
        for i, feat in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break
            attrs = feat.attributes()
            result = {}
            try:
                result = self._run_feature(
                    feat, crops, default_crop, crop_field, plant_field, default_plant, l_fields,
                    stages, mapping, region, to_wgs84, da, is_polygon, pe_fraction, nir_period,
                    efficiency, cache)
            except Exception as exc:  # one bad field must not stop the run
                failures += 1
                result = {"status": "error: {}".format(exc)}
                feedback.reportError("Feature {}: {}".format(feat.id(), exc), fatalError=False)
            out = QgsFeature(out_fields)
            out.setGeometry(feat.geometry())
            out.setAttributes(attrs + [result.get(name, NULL) for name, _, _, _ in RESULT_FIELDS])
            sink.addFeature(out, QgsFeatureSink.FastInsert)
            for d in result.get("_daily", []):
                daily_rows.append([feat.id(), d["day"].isoformat(), d["dekad"], d["stage"],
                                   round(d["Kc"], 3)] + [_csv(d[k]) for k in ("ETo", "ETc", "P", "Pe", "NIR")])
            for p in result.get("_dekad", []):
                dekad_rows.append([feat.id()] + [_csv(p[k]) for k in PERIOD_COLUMNS[1:]])
            feedback.setProgress(100.0 * (i + 1) / total)

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
        if failures:
            feedback.pushWarning("{} feature(s) failed; see the 'status' field.".format(failures))
        return outputs

    def _run_feature(self, feat, crops, default_crop, crop_field, plant_field, default_plant,
                     l_fields, stages, mapping, region, to_wgs84, da, is_polygon, pe_fraction,
                     nir_period, efficiency, cache):
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            raise ValueError("empty geometry")
        crop = default_crop
        if crop_field:
            name = feat[crop_field]
            if name not in (None, NULL) and str(name).strip():
                crop = self._find_crop(crops, str(name))
        plant = (_to_date(feat[plant_field]) if plant_field else None) or default_plant
        stage, stage_note = self._stage(feat, l_fields, crop, stages, mapping, region, plant)

        point = geom.pointOnSurface() if is_polygon else geom.centroid()
        point.transform(to_wgs84)
        p = point.asPoint()
        area = None
        if is_polygon:
            area = da.convertAreaMeasurement(da.measureArea(geom), QgsUnitTypes.AreaSquareMeters)

        r = pipeline.run_field(p.y(), p.x(), crop, stage, plant, area_m2=area,
                               pe_fraction=pe_fraction, nir_period=nir_period,
                               efficiency=efficiency, fetcher=self.fetcher, cache_dir=cache)
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
            "_daily": r["daily"], "_dekad": r["dekad"],
        }


def _csv(v):
    return "" if v is None else round(v, 3) if isinstance(v, float) else v
