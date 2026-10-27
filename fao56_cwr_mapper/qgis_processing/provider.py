"""Processing provider: registers the plugin's algorithms in the QGIS toolbox."""

import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .field_cwr_algorithm import FieldCropWaterRequirement


class FAO56Provider(QgsProcessingProvider):
    def id(self):
        return "fao56cwr"

    def name(self):
        return "FAO-56 Crop Water"

    def longName(self):
        return "FAO-56 Crop Water Requirement Mapper"

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), "icon.png"))

    def loadAlgorithms(self):
        self.addAlgorithm(FieldCropWaterRequirement())
