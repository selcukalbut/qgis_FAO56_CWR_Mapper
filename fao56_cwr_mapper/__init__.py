"""FAO-56 Crop Water Requirement Mapper - QGIS plugin entry point."""


def classFactory(iface):  # noqa: N802 (QGIS API name)
    from .plugin import FAO56CWRMapperPlugin
    return FAO56CWRMapperPlugin(iface)
