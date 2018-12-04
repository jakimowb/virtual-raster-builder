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
from tests import *
QGIS_APP = initQgisApplication()
SHOW_GUI = True
from vrtbuilder import toRasterLayer, toVectorLayer
from vrtbuilder.widgets import *
from vrtbuilder.virtualrasters import *
from vrtbuilder.utils import *
from exampledata import landsat1, landsat2, landsat2_SAD, rapideye
import exampledata
class testclassData(unittest.TestCase):



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
        self.assertTrue(np.array_equal(arr1, arr2))

        VRT.setCrs(QgsCoordinateReferenceSystem('EPSG:4281'))
        ds3 = VRT.saveVRT('/vsimem/ds3.vrt')
        self.assertIsInstance(ds3, gdal.Dataset)
        self.assertEqual(len(VRT), ds3.RasterCount)
        self.assertEqual(len(VRT), ds1.RasterCount)
        self.assertNotEqual(ds1.GetProjection(), ds3.GetProjection())
        arr3 = ds3.ReadAsArray()
        self.assertFalse(np.array_equal(arr1, arr3))
        pass

    def test_vrtRaster(self):

        tmpDir = tempfile.mkdtemp()


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
            path =  os.path.join(tmpDir, 'testEmptyVRT.vrt')

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

    def test_VRTRasterInputSourceBand(self):

        bands1 = VRTRasterInputSourceBand.fromRasterLayer(landsat1)
        bands2 = VRTRasterInputSourceBand.fromGDALDataSet(landsat1)

        self.assertIsInstance(bands1, list)
        self.assertIsInstance(bands2, list)
        self.assertTrue(len(bands1) == len(bands2))

        for b1, b2 in zip(bands1, bands2):
            self.assertIsInstance(b1, VRTRasterInputSourceBand)
            self.assertIsInstance(b2, VRTRasterInputSourceBand)
            self.assertTrue(b2.name() in b1.name())

    def test_describeRaw(self):
        from exampledata import speclib as pathESL

        pathHDR= pathESL.replace('.sli', '.hdr')
        f = open(pathHDR, 'r', encoding='utf-8')
        lines = f.read()
        f.close()

        nl = int(re.search(r'lines[ ]*=[ ]*(?P<n>\d+)', lines).group('n'))
        ns = int(re.search(r'samples[ ]*=[ ]*(?P<n>\d+)', lines).group('n'))
        nb = int(re.search(r'bands[ ]*=[ ]*(?P<n>\d+)', lines).group('n'))
        dt = int(re.search(r'data type[ ]*=[ ]*(?P<n>\d+)', lines).group('n'))
        bo = int(re.search(r'byte order[ ]*=[ ]*(?P<n>\d+)', lines).group('n'))
        byteOrder = 'MSB' if bo != 0 else 'LSB'

        assert dt == 5 #float
        eType = gdal.GDT_Float64

        pathVRT1 = os.path.join(self.tmpDir, 'vrtRawfile.vrt')
        pathVRT2 = '/vsimem/myrawvrt'

        for pathVRT in [pathVRT1, pathVRT2]:
            self.assertTrue(os.path.isfile(pathESL))
            dsVRT = describeRawFile(pathESL, pathVRT, ns, nl, bands=nb, eType=eType, byteOrder=byteOrder)

            self.assertIsInstance(dsVRT, gdal.Dataset)
            self.assertEqual(nb, dsVRT.RasterCount)
            self.assertEqual(ns, dsVRT.RasterXSize)
            self.assertEqual(nl, dsVRT.RasterYSize)

            arr = dsVRT.ReadAsArray()
            if not pathVRT.startswith('/vsi'):
                f = open(pathVRT, 'r', encoding='utf-8')
                xml = f.read()
                f.close()
            else:
                xml = read_vsimem(pathVRT).decode('utf-8')
            self.assertTrue('<ImageOffset>0' in xml)
            self.assertTrue('<PixelOffset>8' in xml)
            self.assertTrue('<LineOffset>1416' in xml)
            self.assertTrue('<ByteOrder>LSB' in xml)


        #this should look like a spectrum
        if True:

            yVals = arr[32,:]
            import pyqtgraph as pg
            #this should look like a vegetation spectrum
            pw = pg.plot(yVals, pen='r')  # plot x vs y in red
            r = QMessageBox.question(None, 'Test', 'Does this look like a vegetation spectrum?')
            self.assertTrue(r == QMessageBox.Yes, 'Did not look like a vegetation spectrum')

        s  =""


    def test_gui(self):
        from exampledata import landsat1
        reg = QgsProject.instance()
        lyr = QgsRasterLayer(landsat1)
        reg.addMapLayer(lyr)
        GUI = VRTBuilderWidget()
        GUI.show()
        GUI.loadSrcFromMapLayerRegistry()
        self.assertTrue(len(GUI.mSourceFileModel), 1)
        files = GUI.mSourceFileModel.rasterSources()
        self.assertTrue(landsat1 in files)

        self.assertIsInstance(GUI.mSourceFileModel.rootNode(), TreeNode)
        child1 = GUI.mSourceFileModel.rootNode().childNodes()[0]
        self.assertIsInstance(child1, SourceRasterFileNode)

        for b in child1.sourceBands():
            self.assertIsInstance(b, VRTRasterInputSourceBand)

        sourceBandIndices = []
        for node in child1.childNodes()[-1].childNodes():
            self.assertIsInstance(node, SourceRasterBandNode)
            idx = GUI.mSourceFileModel.node2idx(node)
            self.assertIsInstance(idx, QModelIndex)
            sourceBandIndices.append(idx)

        # get the first band of first source
        mimeData = GUI.mSourceFileModel.mimeData(sourceBandIndices[0:1])
        self.assertIsInstance(mimeData, QMimeData)
        # drop a source on to the VRTRasterTreeModel
        GUI.mVRTRasterTreeModel.dropMimeData(mimeData, Qt.CopyAction, 0, 0, QModelIndex())
        self.assertTrue(len(GUI.mVRTRaster) == 1)


        if SHOW_GUI:
            QGIS_APP.exec_()

    def test_bounds(self):

        p = exampledata.landsat1

        b1 = RasterBounds.create(p)
        self.assertIsInstance(b1, RasterBounds)

        lyr = QgsRasterLayer(p)
        b2 = RasterBounds.create(lyr)

        self.assertIsInstance(b2, RasterBounds)
        self.assertEqual(b1, b2)

        QGIS_APP.exec_()


    def test_vrtBuilderGUI(self):
        pass


    def test_init(self):

        dsMEM = TestObjects.inMemoryImage(100,20,3)
        self.assertIsInstance(dsMEM, gdal.Dataset)


        sources = [landsat1, gdal.Open(landsat1), QgsRasterLayer(landsat1), dsMEM, dsMEM.GetFileList()[0]]
        for s in sources:
            self.assertIsInstance(toRasterLayer(s), QgsRasterLayer)

        sources = ['foo', None, 234, 42.1]
        for s in sources:
            self.assertEqual(toRasterLayer(s), None)

        pass


        dsVEC = TestObjects.inMemoryVector()
        sources = [dsVEC, dsVEC.GetDescription()]
        for s in sources:
            self.assertIsInstance(toVectorLayer(s), QgsVectorLayer)


if __name__ == "__main__":

    unittest.main()



