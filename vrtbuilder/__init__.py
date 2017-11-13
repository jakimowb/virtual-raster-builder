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
*   the Free Software Foundation; either version 3 of the License, or     *
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
DIR_ROOT = os.path.dirname(DIR)
DIR_UI = os.path.join(DIR,'ui')
DIR_EXAMPLEDATA = os.path.join(DIR_ROOT, 'exampledata')

VERSION = '0.1'
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
import vrtbuilder.ui.resources
vrtbuilder.ui.resources.qInitResources()
