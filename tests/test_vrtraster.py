import unittest

from PyQt5.QtCore import QAbstractItemModel
from osgeo import gdal

from exampledata import Landsat8_West_tif, Landsat8_East_tif
from qgis.core import QgsRasterLayer
from vrtbuilder.qgispluginsupport.qps.testing import start_app, TestCase
from vrtbuilder.virtualrasters import VRTRaster, VRTInputRaster, VRTRasterBand

start_app()


class VRTRasterTests(TestCase):

    def test_VRTInputRaster(self):
        ds = gdal.Open(Landsat8_West_tif.as_posix())

        src = VRTInputRaster(Landsat8_West_tif)
        self.assertEqual(len(src), ds.RasterCount)

    def test_VRTRasterBand(self):
        band = VRTRasterBand()
        band.setName('Virtual Band A')

    def test_VRTRaster(self):
        vrt = VRTRaster()
        self.assertIsInstance(vrt, QAbstractItemModel)

        vrt.insertBands(0, [VRTRasterBand(name='Band A'), VRTRasterBand(name='Band B')])
        self.assertEqual(len(vrt), 2)
        band = vrt[0]
        self.assertIsInstance(band, VRTRasterBand)
        self.assertEqual(band.name(), 'Band A')
        vrt.clear()

        self.assertTrue(vrt.source(Landsat8_West_tif) is None)
        vrt.registerSource(Landsat8_West_tif)
        src = vrt.source(Landsat8_West_tif)
        self.assertIsInstance(src, VRTInputRaster)

        sources = vrt.sources()
        self.assertListEqual(sources, [Landsat8_West_tif])

        lyr = QgsRasterLayer(Landsat8_West_tif.as_posix())
        nb = lyr.bandCount()
        vrt.addSourcesAsStack([Landsat8_West_tif, Landsat8_East_tif])
        self.assertEqual(len(vrt), 2 * nb)
        vrt.clear()

        self.assertEqual(len(vrt), 0)
        vrt.addSourcesAsMosaic([Landsat8_West_tif, Landsat8_East_tif])
        self.assertEqual(len(vrt), nb)

        vrt.clear()

        s = ""


if __name__ == '__main__':
    unittest.main()
