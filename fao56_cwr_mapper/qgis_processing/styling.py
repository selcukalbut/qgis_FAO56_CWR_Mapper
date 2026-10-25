"""Graduated style for the result layer: net irrigation requirement (mm)."""

from qgis.core import (
    QgsClassificationPrettyBreaks,
    QgsGradientColorRamp,
    QgsGradientStop,
    QgsGraduatedSymbolRenderer,
    QgsProcessingLayerPostProcessorInterface,
    QgsRendererRange,
    QgsSymbol,
)
from qgis.PyQt.QtGui import QColor

FIELD = "NIR_mm"
NO_VALUE = -1.0
# ColorBrewer "Blues" (5 classes): light = low, dark = high requirement
BLUES = ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"]


def _ramp():
    stops = [QgsGradientStop(i / (len(BLUES) - 1), QColor(c)) for i, c in enumerate(BLUES[1:-1], 1)]
    return QgsGradientColorRamp(QColor(BLUES[0]), QColor(BLUES[-1]), False, stops)


def _symbol(layer, color):
    sym = QgsSymbol.defaultSymbol(layer.geometryType())
    sym.setColor(color)
    if sym.symbolLayerCount() and hasattr(sym.symbolLayer(0), "setStrokeColor"):
        sym.symbolLayer(0).setStrokeColor(QColor("#4d4d4d"))
    return sym


def nir_renderer(layer, classes=5):
    """Graduated renderer on NIR_mm with 'nice' class breaks.

    Features without a value (errors, incomplete data) get their own grey
    class instead of disappearing from the map.
    """
    idx = layer.fields().indexOf(FIELD)
    if idx < 0:
        return None
    values = sorted(float(f[FIELD]) for f in layer.getFeatures()
                    if f[FIELD] is not None and str(f[FIELD]) != "NULL")
    ranges = []
    if values:
        if values[0] == values[-1]:
            bounds = [(values[0], values[0])]
        else:
            bounds = [(c.lowerBound(), c.upperBound())
                      for c in QgsClassificationPrettyBreaks().classes(values, classes)]
        ramp = _ramp()
        for i, (lo, hi) in enumerate(bounds):
            color = ramp.color(i / (len(bounds) - 1) if len(bounds) > 1 else 0.6)
            ranges.append(QgsRendererRange(lo, hi, _symbol(layer, color),
                                           "{:.0f} – {:.0f} mm".format(lo, hi)))
    grey = _symbol(layer, QColor("#bdbdbd"))
    ranges.append(QgsRendererRange(NO_VALUE, NO_VALUE, grey, "no value (see status)"))
    renderer = QgsGraduatedSymbolRenderer('coalesce("{}", {})'.format(FIELD, NO_VALUE), ranges)
    renderer.setSourceColorRamp(_ramp())
    return renderer


def apply_nir_style(layer):
    """Style the layer; also stores the style as default in a GeoPackage output."""
    renderer = nir_renderer(layer)
    if renderer is None:
        return False
    layer.setRenderer(renderer)
    layer.triggerRepaint()
    source = layer.source().split("|")[0].lower()
    if layer.providerType() == "ogr" and source.endswith(".gpkg"):
        try:
            # saveStyleToDatabaseV2 exists in recent QGIS; the old call is kept for 3.22+
            save = getattr(layer, "saveStyleToDatabaseV2", None) or layer.saveStyleToDatabase
            save("default", "Net irrigation requirement (mm)", True, "")
        except Exception:  # style persistence is a convenience only
            pass
    return True


class NirStylePostProcessor(QgsProcessingLayerPostProcessorInterface):
    """Applies the style when Processing loads the result layer into the project."""

    _instance = None   # keep a Python reference, otherwise the object is garbage collected

    def postProcessLayer(self, layer, context, feedback):  # noqa: N802 (QGIS API name)
        if layer is not None and layer.isValid():
            apply_nir_style(layer)

    @classmethod
    def create(cls):
        cls._instance = NirStylePostProcessor()
        return cls._instance
