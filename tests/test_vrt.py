# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2017-07-17'
__copyright__ = 'Copyright 2017, Benjamin Jakimow'

import unittest, tempfile
from qgis.gui import *
from qgis.core import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtXml import *

import numpy as np

from vrtbuilder.widgets import *
from vrtbuilder.virtualrasters import *
from vrtbuilder.utils import initQgisApplication
from exampledata import landsat1, landsat2, landsat2_SAD, rapideye

QGIS_APP = initQgisApplication()
class testclassData(unittest.TestCase):

    def setUp(self):
        self.gui = VRTBuilderWidget()
        self.gui.show()
        self.tmpDir = tempfile.mkdtemp('testVRT')
    def tearDown(self):
        self.gui.close()

    def test_vsi_support(self):

        VRT = VRTRaster()
        vb1 = VRTRasterBand()
        vb2 = VRTRasterBand()
        vb1.addSource(VRTRasterInputSourceBand.fromGDALDataSet(landsat1)[0])
        vb2.addSource(VRTRasterInputSourceBand.fromGDALDataSet(landsat2_SAD)[0])
        VRT.addVirtualBand(vb1)
        VRT.addVirtualBand(vb2)

        self.assertTrue(len(vb1), 1)
        self.assertTrue(len(vb2), 1)
        self.assertTrue(len(VRT), 2)

        path = '/vsimem/myinmemory.vrt'
        ds1 = VRT.saveVRT(path)
        ds2 = gdal.Open(path)

        self.assertIsInstance(ds1, gdal.Dataset)
        self.assertIsInstance(ds2, gdal.Dataset)
        self.assertEqual(len(VRT), ds1.RasterCount)
        self.assertEqual(len(VRT), ds2.RasterCount)
        self.assertEqual(VRT.crs().toWkt(), ds1.GetProjection())
        arr1 = ds1.ReadAsArray()
        arr2 = ds2.ReadAsArray()
        self.assertTrue(np.all(arr1 == arr2))

        VRT.setCrs(QgsCoordinateReferenceSystem('EPSG:4281'))
        ds3 = VRT.saveVRT('/vsimem/ds3.vrt')
        self.assertIsInstance(ds3, gdal.Dataset)
        self.assertEqual(len(VRT), ds3.RasterCount)
        self.assertEqual(len(VRT), ds1.RasterCount)
        self.assertNotEqual(ds1.GetProjection(), ds3.GetProjection())
        arr3 = ds3.ReadAsArray()
        self.assertFalse(np.all(arr1 == arr3))
        pass

    def test_vrtRaster(self):




        #1. create an empty VRT
        VRT = VRTRaster()

        vb1 = VRTRasterBand()
        vb2 = VRTRasterBand()


        VRT.addVirtualBand(vb1)
        VRT.addVirtualBand(vb2)

        self.assertEqual(len(VRT), 2)
        self.assertEqual(vb2, VRT[1])

        VRT.removeVirtualBand(vb1)
        self.assertEqual(len(VRT), 1)
        self.assertEqual(vb2, VRT[0])


        for n in [0, 2]:
            while not len(VRT) == 0:
                VRT.removeVirtualBand(0)

            for _ in range(n):
                VRT.addVirtualBand(VRTRasterBand())
            path = os.path.join(self.tmpDir, 'testEmptyVRT.vrt')

            if n == 0:
                self.assertRaises(Exception, VRT.saveVRT, path)
                continue

            self.assertIsInstance(VRT.saveVRT(path), gdal.Dataset)

            f = open(path, encoding='utf8')
            xml = ''.join(f.readlines())
            f.close()

            ds = gdal.Open(path)
            self.assertIsInstance(ds, gdal.Dataset)
            self.assertEqual(ds.RasterCount, len(VRT))

        pass

    def test_gui(self):
        from exampledata import landsat1
        reg = QgsProject.instance()
        lyr = QgsRasterLayer(landsat1)
        reg.addMapLayer(lyr)

        self.gui.loadSrcFromMapLayerRegistry()
        self.assertTrue(len(self.gui.sourceFileModel), 1)
        files = self.gui.sourceFileModel.files()
        self.assertTrue(landsat1 in files)

        QGIS_APP.exec_()


    def test_vrtBuilderGUI(self):
        pass

if __name__ == "__main__":

    unittest.main()



