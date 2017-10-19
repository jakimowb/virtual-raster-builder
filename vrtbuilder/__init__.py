# -*- coding: utf-8 -*-

"""
***************************************************************************
    __init__.py
    ---------------------
    Date                 : Oktober 2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
# noinspection PyPep8Naming
from __future__ import absolute_import

import os, sys, fnmatch, site, re
import six, logging
from qgis.core import *
from qgis.gui import *

DIR = os.path.dirname(__file__)
DIR_REPO = os.path.dirname(DIR)
DIR_UI = os.path.join(DIR,'ui')
DIR_EXAMPLEDATA = os.path.join(DIR_REPO, 'exampledata')

VERSION = '0.1'
LICENSE = 'GNU GPL-3'
TITLE = 'Virtual Raster Builder'
DESCRIPTION = 'A QGIS Plugin to create GDAL virtual rasters (VRT) by drag and drop.'
WEBSITE = 'https://bitbucket.org/jakimowb/vrtbuilder'
REPOSITORY = 'https://bitbucket.org/jakimowb/vrtbuilder'
ABOUT = """
The VRT Raster Builder is developed at Humboldt-Universität zu Berlin. 
It is developed under contract by the German Research Centre for Geosciences (GFZ) as part of the EnMAP Core Science Team activities (www.enmap.org), funded by DLR and granted by the Federal Ministry of Economic Affairs and Energy (BMWi, grant no. 50EE1529)
"""
PATH_ICON = os.path.join(DIR_UI,'mActionNewVirtualLayer.png')
import vrtbuilder.ui.resources
vrtbuilder.ui.resources.qInitResources()
