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

import unittest

from tests.testing import *
from tests import testing

QGIS_APP = testing.initQgisApplication()
SHOW_GUI = False
from vrtbuilder.widgets import *
from vrtbuilder.virtualrasters import *
from vrtbuilder.utils import *
from exampledata import landsat1, landsat2, landsat2_SAD


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

        print('\n'.join(vsiFiles()))
        VRT.setCrs(QgsCoordinateReferenceSystem('EPSG:32723'))
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


            self.assertRaises(Exception, VRT.saveVRT, path)
            continue

        ext = VRT.extent()
        self.assertTrue(ext == None)
        band1 = VRT[0]
        self.assertIsInstance(band1, VRTRasterBand)
        band1.addSource(VRTRasterInputSourceBand(landsat1, 0))
        ext = VRT.extent()
        res = VRT.resolution()
        crs = VRT.crs()
        self.assertIsInstance(ext, QgsRectangle)
        self.assertIsInstance(res, QSizeF)
        self.assertIsInstance(crs, QgsCoordinateReferenceSystem)


        #align to other raster grid
        pt = QgsPointXY(ext.xMinimum() - 5, ext.yMaximum() + 3.5)

        lyr = toRasterLayer(landsat2_SAD)
        self.assertIsInstance(lyr, QgsRasterLayer)
        self.assertTrue(lyr.crs() != VRT.crs())
        VRT.alignToRasterGrid(landsat2_SAD)
        self.assertTrue(lyr.crs() == VRT.crs())
        res = QSizeF(lyr.rasterUnitsPerPixelX(), lyr.rasterUnitsPerPixelY())
        self.assertTrue(VRT.resolution() == res)

    def test_vrtRasterMetadata(self):

        ds = gdal.Open(landsat1)
        self.assertIsInstance(ds, gdal.Dataset)
        lyr = toRasterLayer(ds)
        self.assertIsInstance(lyr, QgsRasterLayer)

        VRT = VRTRaster()
        VRT.addFilesAsStack()


    def test_alignExtent(self):

        pxSize = QSizeF(30,30)
        extent = QgsRectangle(30, 210, 300, 600)
        refPoint1 = QgsPointXY(-300, -300)
        refPoint2 = QgsPointXY(10, 10)
        refPoint3 = QgsPointXY(-20, -20)
        refPoint4 = QgsPointXY(20, 20)
        point = QgsPointXY(8,15)
        pt1 = alignPointToGrid(pxSize, refPoint1, point)
        pt2 = alignPointToGrid(pxSize, refPoint1, QgsPointXY(16,16))
        self.assertIsInstance(pt1, QgsPointXY)
        self.assertEqual(pt1, QgsPointXY(0,0))
        self.assertEqual(pt2, QgsPointXY(30,30))

        extent1, px1 = alignRectangleToGrid(pxSize, refPoint1, extent)
        extent2, px2 = alignRectangleToGrid(pxSize, refPoint2, extent)
        extent3, px3 = alignRectangleToGrid(pxSize, refPoint3, extent)
        extent4, px4 = alignRectangleToGrid(pxSize, refPoint4, extent)
        for e in [extent1, extent2, extent3, extent4]:
            self.assertIsInstance(e, QgsRectangle)

        for px in [px1, px2, px3, px4]:
            self.assertIsInstance(px, QSize)


        self.assertTrue(extent1 == extent)
        self.assertTrue(extent2 == QgsRectangle(40, 220, 310, 610))
        self.assertTrue(extent3 == QgsRectangle(40, 220, 310, 610))




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
        self.assertIsInstance(GUI, VRTBuilderWidget)
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

        #make a mouse click on the map canvas to select something
        size = GUI.previewMap.size()
        point = QPointF(0.5 * size.width(), 0.5*size.height())
        event = QMouseEvent(QEvent.MouseButtonPress, point, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        GUI.previewMap.mousePressEvent(event)

        #load more source files
        GUI.addSourceFiles([landsat1, landsat2, landsat2_SAD])
        self.assertTrue(len(GUI.mSourceFileModel.rasterSources()) == 3)


        #test map tools
        for name in ['COPY_EXTENT', 'COPY_GRID', 'ALIGN_GRID', 'COPY_RESOLUTION']:
            GUI.activateMapTool(name)
            canvas = GUI.previewMap
            self.assertIsInstance(canvas, QgsMapCanvas)
            mapTool = canvas.mapTool()
            self.assertIsInstance(mapTool, QgsMapTool)

            layer = None
            extent = None
            crs = None

            if isinstance(mapTool, MapToolIdentifySource):
                def onIdentified(lyr):
                    nonlocal layer
                    layer = lyr
                mapTool.sigMapLayerIdentified.connect(onIdentified)
            elif isinstance(mapTool, MapToolSpatialExtent):
                def onIdentified(e, c):
                    nonlocal extent, crs
                    extent = e
                    crs = c
                mapTool.sigSpatialExtentSelected.connect(onIdentified)

            event = QMouseEvent(QEvent.MouseButtonPress, point, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            GUI.previewMap.mousePressEvent(event)

            if isinstance(mapTool, MapToolIdentifySource):

                self.assertIsInstance(layer, QgsMapLayer)

            elif isinstance(mapTool, MapToolSpatialExtent):

                self.assertIsInstance(extent, QgsRectangle)
                self.assertIsInstance(crs, QgsCoordinateReferenceSystem)



        if SHOW_GUI:
            QGIS_APP.exec_()


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



