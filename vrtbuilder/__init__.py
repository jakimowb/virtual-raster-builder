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



def initQgisApplication(qgisResourceDir:str=None)->QgsApplication:
    """
    Initializes a QGIS Environment
    :return: QgsApplication instance of local QGIS installation
    """
    import qgis.testing
    from qgis.PyQt.QtWidgets import QApplication
    if isinstance(QgsApplication.instance(), QgsApplication):
        return QgsApplication.instance()
    else:

        if not 'QGIS_PREFIX_PATH' in os.environ.keys():
            raise Exception('env variable QGIS_PREFIX_PATH not set')

        if sys.platform == 'darwin':
            # add location of Qt Libraries
            assert '.app' in qgis.__file__, 'Can not locate path of QGIS.app'
            PATH_QGIS_APP = re.search(r'.*\.app', qgis.__file__).group()
            QApplication.addLibraryPath(os.path.join(PATH_QGIS_APP, *['Contents', 'PlugIns']))
            QApplication.addLibraryPath(os.path.join(PATH_QGIS_APP, *['Contents', 'PlugIns', 'qgis']))

        qgsApp = qgis.testing.start_app()

        if not isinstance(qgisResourceDir, str):
            parentDir = os.path.dirname(os.path.dirname(__file__))
            resourceDir = os.path.join(parentDir, 'qgisresources')
            if os.path.exists(resourceDir):
                qgisResourceDir = resourceDir

        if isinstance(qgisResourceDir, str) and os.path.isdir(qgisResourceDir):
            modules = [m for m in os.listdir(qgisResourceDir) if re.search(r'[^_].*\.py', m)]
            modules = [m[0:-3] for m in modules]
            for m in modules:
                mod = importlib.import_module('qgisresources.{}'.format(m))
                if "qInitResources" in dir(mod):
                    mod.qInitResources()


        return qgsApp
