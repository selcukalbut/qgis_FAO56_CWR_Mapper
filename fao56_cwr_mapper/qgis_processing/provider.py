"""Processing provider: registers the plugin's algorithms in the QGIS toolbox."""

from qgis.core import QgsProcessingProvider

from .field_cwr_algorithm import FieldCropWaterRequirement


class FAO56Provider(QgsProcessingProvider):
    def id(self):
        return "fao56cwr"

    def name(self):
        return "FAO-56 Crop Water"

    def longName(self):
        return "FAO-56 Crop Water Requirement Mapper"

    def loadAlgorithms(self):
        self.addAlgorithm(FieldCropWaterRequirement())
