# -*- coding: utf-8 -*-
"""
/***************************************************************************
                              Virtual Raster Builder
                              -------------------
        begin                : 2017-08-04
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 3 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# noinspection PyPep8Naming

import os, site
from qgis.gui import *
from qgis.core import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *


class VRTBuilderPlugin(object):

    def __init__(self, iface):
        self.iface = iface
        assert isinstance(iface, QgisInterface)
        self.vrtBuilder = None
        """
        import console.console as CONSOLE
        if CONSOLE._console is None:
            CONSOLE._console = CONSOLE.PythonConsole(iface.mainWindow())
            QTimer.singleShot(0, CONSOLE._console.activate)
        """

    def initGui(self):

        DIR_REPO = os.path.dirname(__file__)
        site.addsitedir(DIR_REPO)

        # init main UI
        import vrtbuilder
        from vrtbuilder.ui import resources
        resources.qInitResources()

        from vrtbuilder import TITLE, PATH_ICON

        icon = QIcon(':/vrtbuilder/mActionNewVirtualLayer.svg')
        self.action = QAction(icon, TITLE, self.iface)
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        #self.iface.addRasterToolBarIcon(self.action)

    def run(self):
        from vrtbuilder.widgets import VRTBuilderWidget
        self.vrtBuilder = VRTBuilderWidget()
        if isinstance(self.iface, QgisInterface):
            mapCanvas = self.iface.mapCanvas()
            if isinstance(mapCanvas, QgsMapCanvas):
                self.vrtBuilder.registerMapCanvas(mapCanvas)
            self.vrtBuilder.sigRasterCreated.connect(self.iface.addRasterLayer)

        self.vrtBuilder.show()

    def unload(self):

        self.iface.removeToolBarIcon(self.action)
        #self.iface.removeRasterToolBarIcon(self.action)

