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
from __future__ import absolute_import
import os, site, logging
logger = logging.getLogger(__name__)
from qgis.gui import *
from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *



class VRTBuilderPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.vrtBuilder = None
        import console.console as CONSOLE
        if CONSOLE._console is None:
            CONSOLE._console = CONSOLE.PythonConsole(iface.mainWindow())
            QTimer.singleShot(0, CONSOLE._console.activate)

    def initGui(self):
        self.toolbarActions = []

        DIR_REPO = os.path.dirname(__file__)
        site.addsitedir(DIR_REPO)

        # init main UI
        import vrtbuilder
        from vrtbuilder import TITLE, PATH_ICON

        icon = QIcon(PATH_ICON)
        action = QAction(icon, TITLE, self.iface)
        action.triggered.connect(self.run)
        self.toolbarActions.append(action)


        for action in self.toolbarActions:
            self.iface.addToolBarIcon(action)

    def run(self):
        from vrtbuilder.widgets import VRTBuilderWidget
        self.vrtBuilder = VRTBuilderWidget()
        if isinstance(self.iface, QgisInterface):
            self.vrtBuilder.initMapTools(self.iface.mapCanvas())
            self.vrtBuilder.sigRasterCreated.connect(self.iface.addRasterLayer)
        self.vrtBuilder.show()

    def unload(self):
        from vrtbuilder.widgets import VRTBuilderWidget

        #print('Unload plugin')
        for action in self.toolbarActions:
            self.iface.removeToolBarIcon(action)

        if isinstance(self.vrtBuilder, VRTBuilderWidget):
            self.vrtBuilder.close()
            self.vrtBuilder = None


    def tr(self, message):
        return QCoreApplication.translate('TimeSeriesViewerPlugin', message)