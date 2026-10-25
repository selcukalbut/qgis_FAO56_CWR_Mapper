"""Plugin shell. The dialog and Processing provider are added in later steps."""


class FAO56CWRMapperPlugin:
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):  # noqa: N802 (QGIS API name)
        pass

    def unload(self):
        pass
