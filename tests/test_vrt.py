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
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *


class testclassData(unittest.TestCase):

    def setUp(self):

        pass

    def tearDown(self):
        pass

    def test_vrtRaster(self):


        from vrtbuilder.virtualrasters import VRTRaster, VRTRasterBand, VRTRasterInputSourceBand



        pass

    def test_vrtBuilderGUI(self):
        pass

if __name__ == "__main__":

    unittest.main()



