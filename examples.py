# -*- coding: utf-8 -*-

"""
***************************************************************************
    examples
    ---------------------
    Date                 : Oktober 2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 3 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
import os

from vrtbuilder.virtualrasters import VRTRaster
from vrtbuilder.widgets import VRTBuilderWidget
from vrtbuilder import DIR_EXAMPLEDATA
from vrtbuilder.externals.qps.testing import start_app
from vrtbuilder.externals.qps.utils import file_search

qgsApp = start_app()
from vrtbuilder.widgets import VRTBuilderWidget

W = VRTBuilderWidget(None)
W.show()

if True and os.path.isdir(DIR_EXAMPLEDATA):
    files = file_search(DIR_EXAMPLEDATA, '*.tif')
    W.addSourceFiles(files)

# close QGIS
qgsApp.exec_()
qgsApp.exitQgis()

