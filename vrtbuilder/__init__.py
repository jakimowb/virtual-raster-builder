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

import os, sys, fnmatch, site, re, importlib

# skip imports when on RTD, as we can not install the full QGIS environment as required
# https://docs.readthedocs.io/en/stable/builds.html
if not os.environ.get('READTHEDOCS') in ['True', 'TRUE', True]:
    from osgeo import gdal, ogr
    from qgis.core import *
    from qgis.gui import *
    from qgis.PyQt.QtCore import *


DIR = os.path.dirname(__file__)
DIR_REPO = os.path.dirname(DIR)
DIR_UI = os.path.join(DIR, 'ui')
DIR_EXAMPLEDATA = os.path.join(DIR_REPO, 'exampledata')
PATH_CHANGELOG = os.path.join(DIR_REPO, 'CHANGELOG')

VERSION = '0.7' #subversion will be set automatically
LICENSE = 'GNU GPL-3'
TITLE = 'Virtual Raster Builder'
DESCRIPTION = 'A QGIS Plugin to create GDAL Virtual Raster (VRT) files by drag and drop.'
HOMEPAGE = 'https://bitbucket.org/jakimowb/virtual-raster-builder'

REPOSITORY = 'https://bitbucket.org/jakimowb/virtual-raster-builder'
ISSUE_TRACKER = 'https://bitbucket.org/jakimowb/virtual-raster-builder/issues'
AUTHOR='Benjamin Jakimow'
MAIL='benjamin.jakimow@geo.hu-berlin.de'
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


PATH_ICON = os.path.join(DIR_UI, 'mActionNewVirtualLayer.png')
#import vrtbuilder.ui.resources
#vrtbuilder.ui.resources.qInitResources()
__version__ = VERSION


MAPLAYER_STORES = [QgsProject.instance()]


def initResources():
    """
    Loads (or reloads) required Qt resources
    :return:
    """
    try:
        from .ui.resources import qInitResources as initVRTBuilderResources
        initVRTBuilderResources()
    except:
        print('Unable to initialize VRT Builder resources', file=sys.stderr)

    try:
        from .externals.qps.qpsresources import qInitResources as initQPSResources
        initQPSResources()
    except Exception as ex:
        print('Unable to import qps.resources', file=sys.stderr)


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

def toDataset(src, readonly=True)->gdal.Dataset:
    """
    Returns a gdal.Dataset if it can be extracted from src
    :param src: input source
    :param readonly: bool, true by default, set False to upen the gdal.Dataset in update mode
    :return: gdal.Dataset
    """
    ga = gdal.GA_ReadOnly if readonly else gdal.GA_Update
    if isinstance(src, str):
        return gdal.Open(src, ga)
    elif isinstance(src, QgsRasterLayer) and src.dataProvider().name() == 'gdal':
        return toDataset(src.source(), readonly=readonly)
    elif isinstance(src, gdal.Dataset):
        return src
    else:
        return None


def toMapLayer(src)->QgsMapLayer:
    """
    Return a QgsMapLayer if it can be extracted from src
    :param src: any type of input
    :return: QgsMapLayer
    """
    lyr = toRasterLayer(src)
    if isinstance(lyr, QgsMapLayer):
        return lyr
    lyr = toVectorLayer(src)
    if isinstance(lyr, QgsMapLayer):
        return lyr
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
        elif isinstance(src, QUrl) and src.isValid():
            if src.isLocalFile():
                lyr = QgsRasterLayer(src.toLocalFile())
        if isinstance(src, gdal.Dataset):
            lyr = QgsRasterLayer(src.GetFileList()[0], '', 'gdal')
        elif isinstance(src, QgsMapLayer):
            lyr = src
        elif isinstance(src, gdal.Band):
            return toRasterLayer(src.GetDataset())
        

    except Exception as ex:
        print(ex)

    if isinstance(lyr, QgsRasterLayer) and lyr.isValid():
        return lyr
    else:
        return None

