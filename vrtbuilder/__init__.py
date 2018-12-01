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

import os, sys, fnmatch, site, re

from osgeo import gdal, ogr
from qgis.core import *
from qgis.gui import *

DIR = os.path.dirname(__file__)
DIR_ROOT = os.path.dirname(DIR)
DIR_UI = os.path.join(DIR,'ui')
DIR_EXAMPLEDATA = os.path.join(DIR_ROOT, 'exampledata')

VERSION = '0.5'
LICENSE = 'GNU GPL-3'
TITLE = 'Virtual Raster Builder'
DESCRIPTION = 'A QGIS Plugin to create GDAL Virtual Raster (VRT) files by drag and drop.'
WEBSITE = 'https://bitbucket.org/jakimowb/virtual-raster-builder'
REPOSITORY = 'https://bitbucket.org/jakimowb/virtual-raster-builder'
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


PATH_ICON = os.path.join(DIR_UI,'mActionNewVirtualLayer.png')
#import vrtbuilder.ui.resources
#vrtbuilder.ui.resources.qInitResources()
__version__ = VERSION


MAPLAYER_STORES = [QgsProject.instance()]

def registerLayerStore(store):
    assert isinstance(store, (QgsProject, QgsMapLayerStore))
    if store not in MAPLAYER_STORES:
        MAPLAYER_STORES.append(store)

def layerRegistered()->bool:

    return False

def toVectorLayer(src) -> QgsVectorLayer:
    """
    Returns a QgsRasterLayer if it can be extracted from src
    :param src: any type of input
    :return: QgsRasterLayer or None
    """
    lyr = None
    try:
        if isinstance(src, str):
            lyr = QgsVectorLayer(src)
        if isinstance(src, ogr.DataSource):
            path = src.GetDescription()
            bn = os.path.basename(path)
            lyr = QgsVectorLayer(path, bn, 'ogr')
        elif isinstance(src, QgsVectorLayer):
            lyr = src

    except Exception as ex:
        print(ex)

    return lyr

def toRasterLayer(src) -> QgsRasterLayer:
    """
    Returns a QgsRasterLayer if it can be extracted from src
    :param src: any type of input
    :return: QgsRasterLayer or None
    """
    lyr = None
    try:
        if isinstance(src, str):
            lyr = QgsRasterLayer(src)
        if isinstance(src, gdal.Dataset):
            lyr = QgsRasterLayer(src.GetFileList()[0], '', 'gdal')
        elif isinstance(src, QgsMapLayer) :
            lyr = src
        elif isinstance(src, gdal.Band):
            return toRasterLayer(src.GetDataset())

    except Exception as ex:
        print(ex)

    if isinstance(lyr, QgsRasterLayer) and lyr.isValid():
        return lyr
    else:
        return None
