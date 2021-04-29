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

import random
import unittest
import xmlrunner
import tempfile
import sys
import numpy as np
import site
import pathlib
DIR_REPO = pathlib.Path(__file__).parents[1].resolve()
site.addsitedir(DIR_REPO)

from exampledata import Landsat8_West_tif, Landsat8_East_tif, RapidEye_tif, Sentinel2_East_tif, Sentinel2_West_tif
from qgis.core import QgsRectangle, QgsRasterLayer, QgsPointXY, QgsCoordinateReferenceSystem, QgsProject, \
    QgsWkbTypes, QgsMapLayer
from qgis.gui import QgsMapCanvas, QgsMapTool
from vrtbuilder.externals.qps.testing import TestCase, TestObjects
from vrtbuilder import DIR_UI
from vrtbuilder.virtualrasters import alignRectangleToGrid, alignPointToGrid, describeRawFile, read_vsimem
from vrtbuilder.widgets import *

from qgis.core import Qgis

class VRTBuilderTests(TestCase):

    @classmethod
    def setUpClass(cls, resources=[]) -> None:

        resources.append(DIR_UI / 'vrtbuilderresources_rc.py')
        super().setUpClass(resources=resources)

    def test_subdataset(self):

        s = ""

    def test_vsi_support(self):

        VRT = VRTRaster()
        vb1 = VRTRasterBand()
        vb2 = VRTRasterBand()
        vb1.addSource(VRTRasterInputSourceBand.fromGDALDataSet(Landsat8_East_tif)[0])
        vb2.addSource(VRTRasterInputSourceBand.fromGDALDataSet(Landsat8_West_tif)[0])
        VRT.addVirtualBand(vb1)
        VRT.addVirtualBand(vb2)

        self.assertTrue(len(vb1), 1)
        self.assertTrue(len(vb2), 1)
        self.assertTrue(len(VRT), 2)

        path = '/vsimem/myinmemory.vrt'
        ds1: gdal.Dataset = VRT.saveVRT(path)
        ds2 = gdal.Open(path)

        self.assertIsInstance(ds1, gdal.Dataset)
        self.assertIsInstance(ds2, gdal.Dataset)
        self.assertEqual(len(VRT), ds1.RasterCount)
        self.assertEqual(len(VRT), ds2.RasterCount)
        wkt1 = VRT.crs().toWkt()
        wkt2 = ds1.GetProjection()
        crs1 = QgsCoordinateReferenceSystem.fromWkt(wkt1)
        crs2 = QgsCoordinateReferenceSystem.fromWkt(wkt2)
        self.assertEqual(crs1, crs2)
        arr1 = ds1.ReadAsArray()
        arr2 = ds2.ReadAsArray()

        del ds2
        del ds1

        self.assertTrue(np.array_equal(arr1, arr2))

    def test_vrtRaster(self):

        tmpDir = tempfile.mkdtemp()

        # 1. create an empty VRT
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
            path = os.path.join(tmpDir, 'testEmptyVRT.vrt')

            self.assertRaises(Exception, VRT.saveVRT, path)
            continue

        ext = VRT.extent()
        self.assertTrue(ext == None)
        band1 = VRT[0]
        self.assertIsInstance(band1, VRTRasterBand)
        band1.addSource(VRTRasterInputSourceBand(Landsat8_East_tif.as_posix(), 0))
        ext = VRT.extent()
        res = VRT.resolution()
        crs = VRT.crs()
        self.assertIsInstance(ext, QgsRectangle)
        self.assertIsInstance(res, QSizeF)
        self.assertIsInstance(crs, QgsCoordinateReferenceSystem)

        # align to other raster grid
        pt = QgsPointXY(ext.xMinimum() - 5, ext.yMaximum() + 3.5)

        lyr = qgsRasterLayer(RapidEye_tif)
        self.assertIsInstance(lyr, QgsRasterLayer)
        self.assertTrue(lyr.crs() != VRT.crs())
        VRT.alignToRasterGrid(RapidEye_tif)
        self.assertTrue(lyr.crs() == VRT.crs())
        res = QSizeF(lyr.rasterUnitsPerPixelX(), lyr.rasterUnitsPerPixelY())
        self.assertTrue(VRT.resolution() == res)

    def test_read_write_VRT(self):

        lyrSrc1 = TestObjects.createRasterLayer(ns=10, nb=3)
        lyrSrc2 = TestObjects.createRasterLayer(ns=20, nb=5)

        TMP_DIR = self.createTestOutputDirectory()
        os.makedirs(TMP_DIR, exist_ok=True)
        PATH_VRT = TMP_DIR / 'test.vrt'
        VRT = VRTRaster()
        sourceBands1 = VRTRasterInputSourceBand.fromRasterLayer(lyrSrc1)
        sourceBands2 = VRTRasterInputSourceBand.fromRasterLayer(lyrSrc2)

        vBand1 = VRTRasterBand(name='Band1')
        vBand1.addSource(sourceBands1[0])
        vBand1.addSource(sourceBands2[0])

        vBand2 = VRTRasterBand(name='Band2')
        vBand2.addSource(sourceBands1[1])
        vBand2.addSource(sourceBands2[1])

        VRT.addVirtualBand(vBand1)
        VRT.addVirtualBand(vBand2)

        dsVRT = VRT.saveVRT(PATH_VRT)
        self.assertIsInstance(dsVRT, gdal.Dataset)
        self.assertTrue(dsVRT.RasterCount == 2)
        self.assertTrue(dsVRT.GetDriver().ShortName == 'VRT')
        self.assertTrue(VRT.size() == QSize(dsVRT.RasterXSize, dsVRT.RasterYSize))

        # load *.vrt
        VRT2 = VRTRaster()
        VRT2.loadVRT(PATH_VRT)
        self.assertEqual(VRT, VRT2)
        s = ""

    def test_vrtRasterMetadata(self):
        ds = gdal.Open(Landsat8_East_tif.as_posix())
        self.assertIsInstance(ds, gdal.Dataset)
        lyr = qgsRasterLayer(ds)
        self.assertIsInstance(lyr, QgsRasterLayer)
        VRT = VRTRaster()
        VRT.addFilesAsStack([Landsat8_East_tif, Sentinel2_West_tif])

    def test_alignExtent(self):

        pxSize = QSizeF(30, 30)
        extent = QgsRectangle(30, 210, 300, 600)
        refPoint1 = QgsPointXY(-300, -300)
        refPoint2 = QgsPointXY(10, 10)
        refPoint3 = QgsPointXY(-20, -20)
        refPoint4 = QgsPointXY(20, 20)
        point = QgsPointXY(8, 15)
        pt1 = alignPointToGrid(pxSize, refPoint1, point)
        pt2 = alignPointToGrid(pxSize, refPoint1, QgsPointXY(16, 16))
        self.assertIsInstance(pt1, QgsPointXY)
        self.assertEqual(pt1, QgsPointXY(0, 0))
        self.assertEqual(pt2, QgsPointXY(30, 30))

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

        bands1 = VRTRasterInputSourceBand.fromRasterLayer(Landsat8_East_tif)
        bands2 = VRTRasterInputSourceBand.fromGDALDataSet(Landsat8_East_tif)

        self.assertIsInstance(bands1, list)
        self.assertIsInstance(bands2, list)
        self.assertTrue(len(bands1) == len(bands2))

        for b1, b2 in zip(bands1, bands2):
            self.assertIsInstance(b1, VRTRasterInputSourceBand)
            self.assertIsInstance(b2, VRTRasterInputSourceBand)
            self.assertTrue(b2.name() in b1.name())

    def test_core_models(self):

        tv = TreeView()
        model = TreeModel()
        # model.setColumnNames(['A','B','C','D','E'])
        nodeCnt = 0
        lastNode = model.rootNode()

        def addNode(*args):
            nonlocal nodeCnt, lastNode
            nodeCnt += 1
            node = TreeNode(name=f'Node {nodeCnt}')
            rvals = list(range(random.randrange(0, 5)))
            node.setValues([nodeCnt] + rvals)
            lastNode.appendChildNodes(node)
            lastNode = node

        def removeNode(*args):
            nonlocal lastNode
            sm = tv.selectionModel()

            nodes = [idx.data(Qt.UserRole) for idx in sm.selectedIndexes()]
            nodes = [n for n in nodes if isinstance(n, TreeNode)]
            for n in nodes:
                idx = model.node2idx(n)
                if idx.isValid():
                    n.parentNode().removeChildNodes(n)

            lastNode = model.rootNode()

        w = QWidget()
        btnAdd = QPushButton('Add Node')
        btnAdd.clicked.connect(addNode)

        btnRemove = QPushButton('Remove selected')
        btnRemove.clicked.connect(removeNode)

        tv.setModel(model)

        l = QHBoxLayout()
        l.addWidget(btnAdd)
        l.addWidget(btnRemove)
        l2 = QVBoxLayout()
        l2.addLayout(l)
        l2.addWidget(tv)
        w.setLayout(l2)

        btnAdd.click()
        self.showGui(w)

    def test_describeRaw(self):
        from exampledata import speclib as pathESL
        pathESL = pathESL.as_posix()
        pathHDR = pathESL.replace('.sli', '.hdr')

        f = open(pathHDR, 'r', encoding='utf-8')
        lines = f.read()
        f.close()

        nl = int(re.search(r'lines[ ]*=[ ]*(?P<n>\d+)', lines).group('n'))
        ns = int(re.search(r'samples[ ]*=[ ]*(?P<n>\d+)', lines).group('n'))
        nb = int(re.search(r'bands[ ]*=[ ]*(?P<n>\d+)', lines).group('n'))
        dt = int(re.search(r'data type[ ]*=[ ]*(?P<n>\d+)', lines).group('n'))
        bo = int(re.search(r'byte order[ ]*=[ ]*(?P<n>\d+)', lines).group('n'))
        byteOrder = 'MSB' if bo != 0 else 'LSB'

        assert dt == 5  # float
        eType = gdal.GDT_Float64
        tmpDir = tempfile.gettempdir()
        pathVRT1 = os.path.join(tmpDir, 'vrtRawfile.vrt')
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

    def test_gui_empty(self):
        GUI = VRTBuilderWidget()
        reg = QgsProject.instance()
        reg.addMapLayer(TestObjects.createRasterLayer())
        GUI.loadSrcFromMapLayerRegistry()
        self.showGui(GUI)

    def test_gui(self):
        from exampledata import Landsat8_West_tif
        reg = QgsProject.instance()
        reg.addMapLayer(TestObjects.createVectorLayer(QgsWkbTypes.PolygonGeometry))
        reg.addMapLayer(TestObjects.createVectorLayer(QgsWkbTypes.LineGeometry))
        reg.addMapLayer(TestObjects.createVectorLayer(QgsWkbTypes.PointGeometry))
        lyr = QgsRasterLayer(Landsat8_West_tif.as_posix())
        self.assertIsInstance(lyr, QgsRasterLayer)
        self.assertTrue(lyr.width() > 0)
        reg.addMapLayer(lyr)
        GUI = VRTBuilderWidget()
        self.assertIsInstance(GUI, VRTBuilderWidget)
        GUI.show()
        GUI.loadSrcFromMapLayerRegistry()
        self.assertTrue(len(GUI.mSourceFileModel), 1)
        files = GUI.mSourceFileModel.rasterSources()
        self.assertTrue(Landsat8_West_tif.as_posix() in files)

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

        # make a mouse click on the map canvas to select something
        size = GUI.previewMap.size()
        pointCenter = QPointF(0.5 * size.width(), 0.5 * size.height())
        pointLeft = QPointF(0.3 * size.width(), 0.3 * size.height())
        event = QMouseEvent(QEvent.MouseButtonPress, pointCenter, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        GUI.previewMap.mousePressEvent(event)

        # load more source files
        sources = [Landsat8_East_tif, Landsat8_West_tif, Sentinel2_West_tif, Sentinel2_East_tif]
        GUI.addSourceFiles(sources)
        self.assertTrue(len(GUI.mSourceFileModel.rasterSources()) == len(sources))

        canvas = QgsMapCanvas()
        lyrR = TestObjects.createRasterLayer()
        self.assertTrue(lyrR.isValid())
        canvas.setLayers([lyrR])
        canvas.mapSettings().setDestinationCrs(lyrR.crs())
        canvas.setExtent(lyrR.extent())
        pointCenter = QPointF(0.5 * canvas.size().width(), 0.5 * canvas.size().height())
        pointLeft = QPointF(0.3 * canvas.size().width(), 0.3 * canvas.size().height())
        GUI.sigAboutCreateCurrentMapTools.connect(lambda *args, g=GUI, c=canvas: g.createCurrentMapTool(c))
        # test map tools
        for name in VRTBuilderMapTools:
            GUI.setCurrentMapTool(name)

            self.assertIsInstance(canvas, QgsMapCanvas)
            mapTool = canvas.mapTool()
            self.assertIsInstance(mapTool, QgsMapTool)
            self.assertTrue(mapTool in GUI.mMapToolInstances)
            self.assertTrue(len(GUI.mMapToolInstances) == 2)

            layer = None
            extent = None
            crs = None

            def onLayerIdentified(lyr):
                nonlocal layer
                layer = lyr

            def onExtentSelected(c, rect):
                nonlocal extent, crs
                extent = rect
                crs = c

            if isinstance(mapTool, MapToolIdentifySource):
                mapTool.sigMapLayerIdentified.connect(onLayerIdentified)

            elif isinstance(mapTool, SpatialExtentMapTool):
                mapTool.sigSpatialExtentSelected.connect(onExtentSelected)

            # simulate a mouse click
            event = QMouseEvent(QEvent.MouseButtonPress, pointCenter, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            canvas.mousePressEvent(event)
            QApplication.processEvents()

            if isinstance(mapTool, SpatialExtentMapTool):
                # simulate drawing a rectangle
                event = QMouseEvent(QEvent.MouseMove, pointLeft, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
                canvas.mouseMoveEvent(event)

                event = QMouseEvent(QEvent.MouseButtonRelease, pointLeft, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
                canvas.mouseReleaseEvent(event)
                # QApplication.processEvents()

            if isinstance(mapTool, MapToolIdentifySource):


                info = f'python:{sys.version}\nQGIS:{Qgis.QGIS_VERSION}'

                self.assertIsInstance(layer, QgsMapLayer, msg=info)

            elif isinstance(mapTool, SpatialExtentMapTool):

                self.assertIsInstance(extent, QgsRectangle)
                self.assertIsInstance(crs, QgsCoordinateReferenceSystem)

        self.showGui(GUI)

    def test_vrtRasterReprojections(self):

        VRT = VRTRaster()
        vb1 = VRTRasterBand()
        vb2 = VRTRasterBand()
        vb1.addSource(VRTRasterInputSourceBand.fromGDALDataSet(Landsat8_West_tif)[0])
        vb2.addSource(VRTRasterInputSourceBand.fromGDALDataSet(RapidEye_tif)[0])
        VRT.addVirtualBand(vb1)
        VRT.addVirtualBand(vb2)

        crs1 = VRT.crs()
        self.assertIsInstance(crs1, QgsCoordinateReferenceSystem)
        extent1 = VRT.extent()
        res1 = VRT.resolution()
        size1 = VRT.size()

        ul1 = VRT.ul()
        lr1 = VRT.lr()
        self.assertEqual(lr1, QgsPointXY(ul1.x() + size1.width() * res1.width(),
                                         ul1.y() - size1.height() * res1.height()))

        if False:
            # change coordinate system
            crs2 = QgsCoordinateReferenceSystem('EPSG:32721')
            VRT.setCrs(crs2)

            res2 = VRT.resolution()
            size2 = VRT.size()
            extent2 = VRT.extent()
            self.assertIsInstance(res2, QSizeF)
            self.assertAlmostEqual(res1.width(), res2.width(), 2)
            self.assertAlmostEqual(res2.width(), res2.width(), 2)

            ul2 = VRT.ul()
            lr2 = VRT.lr()

            self.assertTrue(ul2.y() > 0, msg='UTM South Y coordinate should be positive.')

            self.assertNotEqual(ul1, ul2)
            self.assertNotEqual(lr1, lr2)

            self.assertEqual(crs2, VRT.crs())
            self.assertEqual(size1, size2)

            self.assertNotEqual(extent1, extent2)
            self.assertAlmostEqual(extent1.width(), extent2.width())
            self.assertAlmostEqual(extent1.height(), extent2.height())

            VRT.setResolution(res1)
            self.assertEqual(extent1.width(), VRT.extent().width())
            self.assertEqual(extent1.height(), VRT.extent().height())

            self.assertIsInstance(crs2, QgsCoordinateReferenceSystem)

            path = '/vsimem/myinmemory.vrt'
            ds1 = VRT.saveVRT(path)
            self.assertIsInstance(ds1, gdal.Dataset)
            data = ds1.ReadAsArray()
            self.assertTrue(data.max() > 0)

            self.assertTrue(data.shape == (len(VRT), VRT.size().height(), VRT.size().width()))
            ds1 = None
            gdal.Unlink(path)

        # convert to degree
        crs3 = QgsCoordinateReferenceSystem('EPSG:4326')
        VRT.setCrs(crs3)
        res3 = VRT.resolution()
        self.assertTrue(res3.width() < 1)
        self.assertTrue(res3.height() < 1)

        path = '/vsimem/myinmemory3.vrt'
        ds1 = VRT.saveVRT(path)
        self.assertIsInstance(ds1, gdal.Dataset)
        data = ds1.ReadAsArray()
        self.assertTrue(data.max() > 0)
        nb, nl, ns = data.shape
        self.assertTrue(nb == len(VRT))
        self.assertTrue(ns == VRT.size().width())
        self.assertTrue(nl == VRT.size().height())

        ds1 = None
        gdal.Unlink(path)

    def test_init(self):

        dsMEM = TestObjects.createRasterDataset(100, 20, 3)
        self.assertIsInstance(dsMEM, gdal.Dataset)

        sources = [Landsat8_East_tif, gdal.Open(Landsat8_East_tif.as_posix()),
                   QgsRasterLayer(Landsat8_East_tif.as_posix()),
                   dsMEM,
                   dsMEM.GetFileList()[0]]
        for s in sources:
            self.assertIsInstance(qgsRasterLayer(s), QgsRasterLayer)


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
