"""Plugin shell: registers the Processing provider. A dialog is added later."""

from qgis.core import QgsApplication


class FAO56CWRMapperPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initProcessing(self):  # noqa: N802 (QGIS API name)
        from .qgis_processing.provider import FAO56Provider
        self.provider = FAO56Provider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):  # noqa: N802 (QGIS API name)
        self.initProcessing()

    def unload(self):
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
