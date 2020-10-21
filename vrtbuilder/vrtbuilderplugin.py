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

import os
import site

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.gui import QgisInterface

class VRTBuilderPlugin(object):

    def __init__(self, iface):
        self.iface = iface
        assert isinstance(iface, QgisInterface)
        self.vrtBuilder = None

    def initGui(self):

        DIR_REPO = os.path.dirname(__file__)
        site.addsitedir(DIR_REPO)

        # init main UI
        from vrtbuilder.ui import vrtbuilderresources_rc
        vrtbuilderresources_rc.qInitResources()

        from vrtbuilder import TITLE

        icon = QIcon(':/vrtbuilder/mActionNewVirtualLayer.svg')

        self.action = QAction(icon, TITLE, self.iface)
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)

        self.iface.addPluginToRasterMenu(self.action.text(), self.action)

    def run(self):
        from vrtbuilder.widgets import VRTBuilderWidget
        self.vrtBuilder = VRTBuilderWidget()
        self.vrtBuilder.show()

    def unload(self):

        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginRasterMenu(self.action.text(), self.action)
