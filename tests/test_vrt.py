# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""
from __future__ import absolute_import
__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2017-07-17'
__copyright__ = 'Copyright 2017, Benjamin Jakimow'

import unittest
from qgis.gui import *
from qgis.core import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *

from vrtbuilder.widgets import *
from vrtbuilder.virtualrasters import *
from vrtbuilder.utils import initQgisApplication

QGIS_APP = initQgisApplication()
class testclassData(unittest.TestCase):

    def setUp(self):
        self.gui = VRTBuilderWidget()
        self.gui.show()

    def tearDown(self):
        self.gui.close()

    def test_gui(self):
        from exampledata import landsat1
        reg = QgsProject.instance()
        lyr = QgsRasterLayer(landsat1)
        reg.addMapLayer(lyr)

        self.gui.loadSrcFromMapLayerRegistry()
        self.assertTrue(len(self.gui.sourceFileModel), 1)
        s = ""

    def test_vrtRaster(self):


        from vrtbuilder.virtualrasters import VRTRaster, VRTRasterBand, VRTRasterInputSourceBand

        #1. create an empty VRT
        VRT = VRTRaster()

        VRT.setCrs()


        pass

    def test_vrtBuilderGUI(self):
        pass

if __name__ == "__main__":

    unittest.main()



