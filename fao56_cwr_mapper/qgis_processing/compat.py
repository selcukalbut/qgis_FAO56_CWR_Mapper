"""Enum and field type names that work on QGIS 3.22+ (Qt5) and QGIS 4 (Qt6).

Newer QGIS versions moved many enums into the Qgis namespace (3.30-3.36) and
Qt6 drops QVariant type constants. Each name below is resolved once: the new
spelling when this QGIS has it, otherwise the QGIS 3.22 spelling.
"""

from qgis.core import (
    Qgis,
    QgsBlockingNetworkRequest,
    QgsFeatureSink,
    QgsField,
    QgsProcessing,
    QgsProcessingParameterDateTime,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsUnitTypes,
    QgsWkbTypes,
)


def _first(*candidates):
    """Value of the first attribute path that exists, e.g. (Qgis, "AreaUnit", "SquareMeters")."""
    for owner, *names in candidates:
        value = owner
        try:
            for name in names:
                value = getattr(value, name)
        except AttributeError:
            continue
        return value
    raise AttributeError("none of the names exist: {}".format(candidates))


SOURCE_POLYGON = _first((Qgis, "ProcessingSourceType", "VectorPolygon"),
                        (QgsProcessing, "TypeVectorPolygon"))
SOURCE_POINT = _first((Qgis, "ProcessingSourceType", "VectorPoint"),
                      (QgsProcessing, "TypeVectorPoint"))
FIELD_ANY = _first((Qgis, "ProcessingFieldParameterDataType", "Any"),
                   (QgsProcessingParameterField, "Any"))
FIELD_STRING = _first((Qgis, "ProcessingFieldParameterDataType", "String"),
                      (QgsProcessingParameterField, "String"))
FIELD_NUMERIC = _first((Qgis, "ProcessingFieldParameterDataType", "Numeric"),
                       (QgsProcessingParameterField, "Numeric"))
DATETIME_DATE = _first((Qgis, "ProcessingDateTimeParameterDataType", "Date"),
                       (QgsProcessingParameterDateTime, "Date"))
NUMBER_DOUBLE = _first((Qgis, "ProcessingNumberParameterType", "Double"),
                       (QgsProcessingParameterNumber, "Double"))
FLAG_ADVANCED = _first((Qgis, "ProcessingParameterFlag", "Advanced"),
                       (QgsProcessingParameterDefinition, "FlagAdvanced"))
GEOMETRY_POLYGON = _first((Qgis, "GeometryType", "Polygon"),
                          (QgsWkbTypes, "PolygonGeometry"))
AREA_SQUARE_METERS = _first((Qgis, "AreaUnit", "SquareMeters"),
                            (QgsUnitTypes, "AreaSquareMeters"))
FAST_INSERT = _first((QgsFeatureSink, "Flag", "FastInsert"),
                     (QgsFeatureSink, "FastInsert"))
NETWORK_NO_ERROR = _first((QgsBlockingNetworkRequest, "ErrorCode", "NoError"),
                          (QgsBlockingNetworkRequest, "NoError"))

# QgsField takes a QMetaType.Type from QGIS 3.38 on; QVariant types before that
_USE_QMETATYPE = Qgis.QGIS_VERSION_INT >= 33800
if _USE_QMETATYPE:
    from qgis.PyQt.QtCore import QMetaType
    _TYPES = {"string": QMetaType.Type.QString, "double": QMetaType.Type.Double,
              "int": QMetaType.Type.Int, "date": QMetaType.Type.QDate}
else:
    from qgis.PyQt.QtCore import QVariant
    _TYPES = {"string": QVariant.String, "double": QVariant.Double,
              "int": QVariant.Int, "date": QVariant.Date}


def make_field(name, kind, length=0, precision=0):
    """QgsField of kind 'string', 'double', 'int' or 'date'."""
    return QgsField(name, _TYPES[kind], len=length, prec=precision)
