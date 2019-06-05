        # -*- coding: utf-8 -*-
"""
/***************************************************************************
                              EO Time Series Viewer
                              -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# noinspection PyPep8Naming

import os, re, io, importlib, uuid
from qgis.core import *
import numpy as np
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from .externals.qps.testing import TestObjects, initQgisApplication
from .externals.qps.utils import file_search
from osgeo import ogr, osr, gdal, gdal_array
import exampledata


def testRasterFiles()->list:
    return list(file_search(os.path.dirname(exampledata.__file__), '*.tif', recursive=True))



class TestObjects(TestObjects):
    
    pass
    