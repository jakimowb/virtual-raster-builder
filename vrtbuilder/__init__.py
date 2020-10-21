# -*- coding: utf-8 -*-

"""
***************************************************************************
    __init__.py
    ---------------------
    Date                 : Oktober 2017
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
# noinspection PyPep8Naming

import os
import sys
import pathlib

# skip imports when on RTD, as we can not install the full QGIS environment as required
# https://docs.readthedocs.io/en/stable/builds.html
if not os.environ.get('READTHEDOCS') in ['True', 'TRUE', True]:
    from osgeo import gdal, ogr
    from qgis.core import *
    from qgis.PyQt.QtCore import *
    from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer, QgsMapLayer, QgsMapLayerStore

__version__ = '0.9'  # subversion will be set automatically
VERSION = __version__

DIR = pathlib.Path(__file__).parent
DIR_REPO = DIR.parent
DIR_UI = DIR / 'ui'
DIR_EXAMPLEDATA = DIR_REPO / 'exampledata'
PATH_CHANGELOG = DIR_REPO / 'CHANGELOG'
PATH_ICON = os.path.join(DIR_UI, 'mActionNewVirtualLayer.png')
LICENSE = 'GNU GPL-3'
TITLE = 'Virtual Raster Builder'
DESCRIPTION = 'A QGIS Plugin to create GDAL Virtual Raster (VRT) files by drag and drop.'
HOMEPAGE = 'https://bitbucket.org/jakimowb/virtual-raster-builder'
DOCUMENTATION = 'https://virtual-raster-builder.readthedocs.io/en/latest/'

REPOSITORY = 'https://bitbucket.org/jakimowb/virtual-raster-builder'
ISSUE_TRACKER = 'https://bitbucket.org/jakimowb/virtual-raster-builder/issues'
AUTHOR = 'Benjamin Jakimow'
MAIL = 'benjamin.jakimow@geo.hu-berlin.de'
ABOUT = """
The VRT Builder is a plugin to create GDAL Virtual Raster (VRT) files by drag and drop. 
It helps to create new images by stacking or mosaicing of source image bands, as well as to 
describe band- and spatial subsets. 

The VRT Builder is developed at Geographic Institute of Humboldt-Universität zu Berlin within the EnMAP-Box 
project under contract of the German Research Centre for Geosciences (GFZ). 

The EnMAP-Box project is part of the EnMAP Core Science Team activities (www.enmap.org), funded by the 
German Aerospace Center (DLR) and granted by the Federal Ministry of 
Economic Affairs and Energy (BMWi, grant no. 50EE1529).
"""
URL_QGIS_RESOURCES = r'https://bitbucket.org/jakimowb/qgispluginsupport/downloads/qgisresources.zip'
URL_HOMEPAGE = 'https://virtual-raster-builder.readthedocs.io'
URL_ISSUETRACKER = 'https://bitbucket.org/jakimowb/virtual-raster-builder/issues'
URL_REPOSITORY = 'https://bitbucket.org/jakimowb/virtual-raster-builder'

MAPLAYER_STORES = [QgsProject.instance()]
