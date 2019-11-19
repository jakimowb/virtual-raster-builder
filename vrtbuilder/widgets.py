# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    widgets
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

import os, pickle, re, os, sys

from collections import OrderedDict

from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtXml import *
from osgeo import gdal, osr, gdalconst as gc

from .models import TreeModel, TreeNode, TreeView
from .virtualrasters import *
from .utils import *
from .externals.qps.maptools import SpatialExtentMapTool
from vrtbuilder import registerLayerStore, MAPLAYER_STORES
from . import toRasterLayer, toMapLayer, toVectorLayer

LUT_FILEXTENSIONS = {}



MDK_BANDLIST = 'hub.vrtbuilder/bandlist'
MDK_INDICES = 'hub.vrtbuilder/vrt.indices'

for i in range(gdal.GetDriverCount()):
    drv = gdal.GetDriver(i)
    assert isinstance(drv, gdal.Driver)

    extensions = drv.GetMetadataItem(gc.DMD_EXTENSIONS)
    if extensions is None:
        extensions = ''

    extensions = extensions.split(' ')
    extensions = [e for e in extensions if e not in [None, '']]
    shortName = drv.ShortName

    if not (drv.GetMetadataItem(gc.DCAP_CREATE) == 'YES' or
                    drv.GetMetadataItem(gc.DCAP_CREATECOPY) == 'YES'):
        continue

    # handle driver specific extensions
    if shortName == 'ENVI':
        extensions.extend(['bsq', 'bil', 'bip'])
    elif shortName == 'Terragen':
        extensions.extend(['.ter'])

    for e in extensions:
        e = '.' + e
        if e not in LUT_FILEXTENSIONS.keys():
            LUT_FILEXTENSIONS[e] = shortName
        else:
            s = ""



def sourceBaseName(source)->str:
    """
    
    :param source: 
    :return: 
    """
    if isinstance(source, str):
        return os.path.basename(source)
    elif isinstance(source, QgsRasterLayer):
        if source.dataProvider().name() == 'gdal':
            return os.path.basename(source.source())
        else:
            return source.name()
    elif isinstance(source, QgsVectorLayer):
        if source.dataProvider().name() == 'ogr':
            return os.path.basename(source.source())
        else:
            return source.name()
        
    elif isinstance(source, QgsMapLayer):
        return source.name()
    
    return str(source)
    


def sourceIcon(source)->QIcon:
    """
    Returns a QgsMapLayer icon 
    :param layer: QgsMapLayer | str (considered as Raster)
    :return: QIcon
    """
    if isinstance(source, str):
        return QIcon(r':/images/themes/default/mIconRaster.svg')
    elif isinstance(source, QgsRasterLayer):
        return QIcon(r':/images/themes/default/mIconRaster.svg')
    elif isinstance(source, QgsVectorLayer):
        if source.geometryType() == QgsWkbTypes.PolygonGeometry:
            return QIcon(r':/images/themes/default/mIconPolygonLayer.svg')
        elif source.geometryType() == QgsWkbTypes.LineGeometry:
            return QIcon(r':/images/themes/default/mIconLineLayer.svg')
        elif source.geometryType() == QgsWkbTypes.PointGeometry:
            return QIcon(r':/images/themes/default/mIconPointLayer.svg')
        else:
            return QIcon(r':/images/themes/default/mIconVector.svg')
    else:
        return QIcon()


class SourceRasterBandNode(TreeNode):
    def __init__(self, parentNode, vrtRasterInputSourceBand):
        assert isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand)
        super(SourceRasterBandNode, self).__init__(parentNode)
        self.setIcon(QIcon(":/vrtbuilder/mIconRaster.svg"))
        self.mSrcBand = vrtRasterInputSourceBand
        self.setName('{}:{}'.format(os.path.basename(self.mSrcBand.mSource), self.mSrcBand.mBandIndex + 1))
        self.setValues([self.mSrcBand.mBandName])
        self.setToolTip('band {}:{}'.format(self.mSrcBand.mBandIndex + 1, self.mSrcBand.mSource))


class VRTRasterNode(TreeNode):
    def __init__(self, parentNode, vrtRaster):
        assert isinstance(vrtRaster, VRTRaster)

        super(VRTRasterNode, self).__init__(parentNode)
        self.mVRTRaster = vrtRaster
        self.mVRTRaster.sigBandInserted.connect(self.onBandInserted)
        self.mVRTRaster.sigBandRemoved.connect(self.onBandRemoved)

    def onBandInserted(self, index, vrtRasterBand):
        assert isinstance(vrtRasterBand, VRTRasterBand)
        i = vrtRasterBand.bandIndex()
        assert i == index
        node = VRTRasterBandNode(self, vrtRasterBand)
        self.insertChildNodes(i, [node])

    def onBandRemoved(self, removedIdx):
        self.removeChildNodes(removedIdx, 1)


class VRTRasterBandNode(TreeNode):
    def __init__(self, parentNode, virtualBand):
        assert isinstance(virtualBand, VRTRasterBand)

        super(VRTRasterBandNode, self).__init__(parentNode)
        self.mVirtualBand = virtualBand

        self.setName(virtualBand.name())
        self.setIcon(QIcon(":/vrtbuilder/mIconVirtualRaster.svg"))
        # self.nodeBands = TreeNode(self, name='Input Bands')
        # self.nodeBands.setToolTip('Source bands contributing to this virtual raster band')
        self.nodeBands = self
        virtualBand.sigNameChanged.connect(self.setName)
        virtualBand.sigSourceInserted.connect(lambda _, src: self.onSourceInserted(src))
        virtualBand.sigSourceRemoved.connect(self.onSourceRemoved)
        for src in self.mVirtualBand:
            self.onSourceInserted(src)

    def onSourceInserted(self, inputSource):
        assert isinstance(inputSource, VRTRasterInputSourceBand)
        assert inputSource.virtualBand() == self.mVirtualBand
        i = self.mVirtualBand.mSources.index(inputSource)

        node = VRTRasterInputSourceBandNode(self, inputSource)
        self.nodeBands.insertChildNodes(i, node)

    def onSourceRemoved(self, row, inputSource):
        assert isinstance(inputSource, VRTRasterInputSourceBand)

        node = self.nodeBands.childNodes()[row]
        if node.mSrc != inputSource:
            s = ""
        self.nodeBands.removeChildNode(node)


class VRTRasterInputSourceBandNode(TreeNode):
    def __init__(self, parentNode, vrtRasterInputSourceBand):
        assert isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand)
        super(VRTRasterInputSourceBandNode, self).__init__(parentNode)
        self.setIcon(QIcon(":/vrtbuilder/mIconRaster.svg"))
        self.mSrc = vrtRasterInputSourceBand
        name = '{}:{}'.format(os.path.basename(self.mSrc.source()), self.mSrc.bandIndex() + 1)
        self.setName(name)
        # self.setValues([self.mSrc.mPath, self.mSrc.mBandIndex])

    def sourceBand(self)->VRTRasterInputSourceBand:
        return self.mSrc

    def source(self)->str:
        return self.mSrc.source()


class VRTRasterPreviewMapCanvas(QgsMapCanvas):
    def __init__(self, parent=None, *args, **kwds):
        super(VRTRasterPreviewMapCanvas, self).__init__(parent, *args, **kwds)
        #self.setCrsTransformEnabled(True)

        self.mVRTRaster = None
        self.mExtentRubberBand = QgsRubberBand(self, QgsWkbTypes.PolygonGeometry)
        self.mExtentRubberBand.setColor(QColor('orange'))
        self.mExtentRubberBand.setWidth(1)

        self.mSelectedSourceRubberBand = QgsRubberBand(self, QgsWkbTypes.PolygonGeometry)
        self.mSelectedSourceRubberBand.setColor(QColor('red'))
        self.mSelectedSourceRubberBand.setWidth(2)

        self.mStore = QgsMapLayerStore()

    def setExtentLineColor(self, color:QColor):
        assert isinstance(color, QColor)
        self.mExtentRubberBand.setColor(color)

    def setExtentLineWidth(self, width:int):
        self.mExtentRubberBand.setWidth(width)

    def extentLineColor(self)->QColor:
        return self.mExtentRubberBand.color()

    def extentLineWidth(self)->int:
        return self.mExtentRubberBand.width()

    def crs(self)->QgsCoordinateReferenceSystem:
        return self.mapSettings().destinationCrs()

    def setVRTRaster(self, vrtRaster:VRTRaster):
        """

        :param vrtRaster:
        :return:
        """
        assert isinstance(vrtRaster, VRTRaster)
        self.mVRTRaster = vrtRaster
        self.mVRTRaster.sigExtentChanged.connect(self.onExtentChanged)
        self.mVRTRaster.sigCrsChanged.connect(self.setDestinationCrs)

    def onExtentChanged(self, *args):

        self.mExtentRubberBand.reset()
        if isinstance(self.mVRTRaster, VRTRaster):
            extent = self.mVRTRaster.extent()
            crs = self.mVRTRaster.crs()
            if isinstance(extent, QgsRectangle) and isinstance(crs, QgsCoordinateReferenceSystem) and extent.width() > 0:
                geom = QgsGeometry.fromWkt(extent.asWktPolygon())
                self.mExtentRubberBand.addGeometry(geom, crs=crs)


    def contextMenuEvent(self, event):
        menu = QMenu()
        action = menu.addAction('Refresh')
        action.triggered.connect(self.refresh)

        action = menu.addAction('Reset')
        action.triggered.connect(self.reset)

        menu.exec_(event.globalPos())

    def setSelectedLayers(self, layers:list):

        self.mSelectedSourceRubberBand.reset()
        for layer in layers:
            assert isinstance(layer, QgsMapLayer)
            geom = QgsGeometry.fromWkt(layer.extent().asWktPolygon())
            self.mSelectedSourceRubberBand.addGeometry(geom, crs = layer.crs())

        if self.extent().width() == 0:
            self.setExtent(self.mSelectedSourceRubberBand.rect())



    def setLayerSet(self, layers):
        raise DeprecationWarning()

    def setLayers(self, layers):
        assert isinstance(layers, list)

        n = len(self.layers())
        self.mStore.addMapLayers(layers)
        super(VRTRasterPreviewMapCanvas, self).setLayers(layers)

        if n == 0 and len(layers) > 0:
            self.setDestinationCrs(layers[0].crs())
            self.setExtent(self.fullExtent())


    def reset(self, *args):
        extent = self.fullExtent()
        extent.scale(1.05)
        self.setExtent(extent)



        self.refresh()


class SourceRasterFileNode(TreeNode):

    def __init__(self, parentNode, mapLayer:QgsRasterLayer):
        super(SourceRasterFileNode, self).__init__(parentNode)
        assert isinstance(mapLayer, QgsRasterLayer)
        assert mapLayer.dataProvider().name() == 'gdal'
        self.mRasterLayer = mapLayer
        self.mPath = mapLayer.source()

        name = mapLayer.name()
        if name == '':
            name = os.path.basename(mapLayer.source())
        self.setName(name)
        srcNode = TreeNode(self, name='Path')
        srcNode.setValues(mapLayer.source())

        # populate metainfo
        crsNode = TreeNode(self, name='CRS')
        crsNode.setIcon(QIcon(':/vrtbuilder/CRS.svg'))
        crs = self.mRasterLayer.crs()
        authInfo = crs.authid()
        #crsNode.setValues([authInfo, crs.ExportToWkt()])
        crsNode.setValues([authInfo, crs.toWkt()])
        self.bandNode = TreeNode(None, name='Bands')
        for b in range(self.mRasterLayer.bandCount()):
            bandName = self.mRasterLayer.bandName(b+1)
            inputSource = VRTRasterInputSourceBand(self.mPath, b, bandName=bandName)
            inputSource.mBandName = bandName
            inputSource.mNoData = self.mRasterLayer.dataProvider().sourceNoDataValue(b+1)

            SourceRasterBandNode(self.bandNode, inputSource)
        self.bandNode.setParentNode(self)
        self.appendChildNodes(self.bandNode)

    def sourceBands(self):
        return [n.mSrcBand for n in self.bandNode.mChildren if isinstance(n, SourceRasterBandNode)]

    def rasterLayer(self)->QgsRasterLayer:
        return self.mRasterLayer


class SourceRasterFilterModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super(SourceRasterFilterModel, self).__init__(parent)

    def mimeTypes(self):
        return self.sourceModel().mimeTypes()

    def dropMimeData(self, mimeData, action, row, col, parentIndex):
        return self.sourceModel().dropMimeData(mimeData, action, row, col, parentIndex)

    def supportedDropActions(self):
        return self.sourceModel().supportedDropActions()



    def canDropMimeData(self, data, action, row, column, parent):
        return self.sourceModel().canDropMimeData(data, action, row, column, parent)

    def filterAcceptsRow(self, sourceRow, sourceParent):
        node = self.sourceModel().idx2node(sourceParent).childNodes()[sourceRow]

        if type(node) not in [SourceRasterFileNode, SourceRasterBandNode]:
            return True

        s0 = self.sourceModel().index(sourceRow, 0, sourceParent).data()
        s1 = self.sourceModel().index(sourceRow, 1, sourceParent).data()

        reg = self.filterRegExp()
        if reg.isEmpty():
            return True

        if isinstance(node, SourceRasterFileNode):
            pattern = reg.pattern().replace(':', '')
            reg.setPattern(pattern)

        return reg.indexIn(s0) >= 0 or reg.indexIn(s1) >= 0

    def filterAcceptsColumn(self, sourceColumn, sourceParent):
        node = self.sourceModel().idx2node(sourceParent)
        if not isinstance(node, SourceRasterBandNode):
            return True
        else:
            return sourceColumn in [0, 1]


class SourceRasterModel(TreeModel):
    sigSourcesAdded = pyqtSignal(list)
    sigSourcesRemoved = pyqtSignal(list)

    def __init__(self, parent=None):
        super(SourceRasterModel, self).__init__(parent)

        self.mColumnNames = ['File/Band', 'Value/Description']


    def __len__(self):
        return len(self.rasterSources())


    def __iter__(self):
        return iter(self.rasterSources())


    def __contains__(self, file):
        return file in self.rasterSources()




    def rasterSources(self)->list:

        return [l.source() for l in self.rasterLayers()]

    def rasterLayers(self)->list:
        """
        Returns the list of QgsRasterLayers behind all input sources.
        :return: [list-of-QgsRasterLayers]
        """
        return [n.rasterLayer() for n in self.mRootNode.childNodes() if isinstance(n, SourceRasterFileNode)]


    def addSource(self, rasterSource):
        self.addSources([rasterSource])

    def addSources(self, rasterSources):
        assert isinstance(rasterSources, list)
        existingSources = self.rasterSources()

        newLayers = [toRasterLayer(s) for s in rasterSources]
        newLayers = [l for l in newLayers if isinstance(l, QgsRasterLayer) and l.source() not in existingSources]

        if len(newLayers) > 0:
            for lyr in newLayers:
                SourceRasterFileNode(self.mRootNode, lyr)
            self.sigSourcesAdded.emit(newLayers)

    def file2node(self, file:str)->SourceRasterFileNode:
        for node in self.mRootNode.childNodes():
            if isinstance(node, SourceRasterFileNode) and node.mPath == file:
                return node
        return None

    def file2layer(self, file:str)->QgsRasterLayer:
        node = self.file2node(file)
        if isinstance(node, SourceRasterFileNode):
            return node.rasterLayer()
        else:
            return None
    def removeFiles(self, listOfFiles):
        assert isinstance(listOfFiles, list)

        toRemove = [n for n in self.mRootNode.childNodes() \
                    if isinstance(n, SourceRasterFileNode) and n.mPath in listOfFiles]
        if len(toRemove) > 0:
            for n in toRemove:
                n.parentNode().removeChildNode(n)
            self.sigSourcesRemoved.emit(toRemove)

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsDropEnabled

        node = self.idx2node(index)

        flags = super(SourceRasterModel, self).flags(index)

        # return flags
        if isinstance(node, SourceRasterFileNode) or \
                isinstance(node, SourceRasterBandNode):
            flags |= Qt.ItemIsDragEnabled
        return flags

    def dropMimeData(self, mimeData, action, row, col, parentIndex):

        assert isinstance(mimeData, QMimeData)

        if mimeData.hasUrls():
            self.addSources(mimeData.urls())
            return True

        elif 'application/qgis.layertreemodeldata' in mimeData.formats():
            doc = QDomDocument()
            doc.setContent(mimeData.data('application/qgis.layertreemodeldata'))
            #types.append('application/qgis.layertreemodeldata')
            #types.append('application/x-vnd.qgis.qgis.uri')
            #print(doc.toString())
            layers = doc.elementsByTagName('layer-tree-layer')
            paths = []
            for i in range(layers.count()):
                node = layers.item(i).toElement()
                assert isinstance(node, QDomElement)
                if node.attribute('providerKey') == 'gdal':
                    paths.append(node.attribute('source'))

            self.addSources(paths)
            return True

        return False

    def contextMenu(self):

        return None

    def mimeTypes(self):
        # specifies the mime types handled by this model
        types = []
        types.append('text/uri-list')
        types.append('application/qgis.layertreemodeldata')
        types.append('application/x-vnd.qgis.qgis.uri')
        return types

    def mimeData(self, indexes)->QMimeData:
        indexes = sorted(indexes)
        if len(indexes) == 0:
            return None
        nodes = []
        for i in indexes:
            n = self.idx2node(i)
            if n not in nodes:
                nodes.append(n)

        sourceBands = []

        for node in nodes:
            if isinstance(node, SourceRasterFileNode):
                sourceBands.extend(node.sourceBands())
            if isinstance(node, SourceRasterBandNode):
                sourceBands.append(node.mSrcBand)

        sourceBands = list(OrderedDict.fromkeys(sourceBands))
        uriList = [sourceBand.mSource for sourceBand in sourceBands]
        uriList = list(OrderedDict.fromkeys(uriList))

        mimeData = QMimeData()

        if len(sourceBands) > 0:
            mimeData.setData(MDK_BANDLIST, pickle.dumps(sourceBands))

        # set text/uri-list
        if len(uriList) > 0:
            mimeData.setUrls([QUrl(p) for p in uriList])
            # mimeData.setText('\n'.join(uriList))
        return mimeData


class VRTSelectionModel(QItemSelectionModel):
    def __init__(self, vrtRasterModel, sourceRasterModel:SourceRasterModel, mapCanvas:VRTRasterPreviewMapCanvas, parent=None):
        assert isinstance(vrtRasterModel, VRTRasterTreeModel)
        assert isinstance(sourceRasterModel, SourceRasterModel)
        assert isinstance(mapCanvas, VRTRasterPreviewMapCanvas)
        # assert isinstance(mapCanvas, VRTRasterPreviewMapCanvas)
        super(VRTSelectionModel, self).__init__(vrtRasterModel, parent)

        self.mPreviewMapHighlights = {}

        self.mVRTRasterModel = vrtRasterModel
        self.mSourceRasterModel = sourceRasterModel
        self.mCanvas = mapCanvas
        self.mRubberBand = QgsRubberBand(self.mCanvas, QgsWkbTypes.PolygonGeometry)
        self.selectionChanged.connect(self.onTreeSelectionChanged)

        self.previewMapTool = QgsMapToolEmitPoint(self.mCanvas)
        self.previewMapTool.setCursor(Qt.ArrowCursor)
        self.previewMapTool.canvasClicked.connect(self.onMapFeatureIdentified)
        self.mCanvas.setMapTool(self.previewMapTool)


    def onMapFeatureIdentified(self, point, button):
        assert isinstance(point, QgsPointXY)
        layers = self.mCanvas.layers()
        mtp = self.mCanvas.mapSettings().mapToPixel()
        newSelection = []
        if self.sender() == self.previewMapTool:
            crs = self.previewMapTool.canvas().crs()
            for lyr in self.mCanvas.layers():
                assert isinstance(lyr, QgsMapLayer)
                ext = lyr.extent()
                assert isinstance(ext, QgsRectangle)

                trans = QgsCoordinateTransform()
                trans.setSourceCrs(lyr.crs())
                trans.setDestinationCrs(crs)
                ext = trans.transform(ext)
                assert isinstance(ext, QgsRectangle)
                if ext.contains(point):
                    newSelection.append(lyr)

            oldSelection = self.selectedSourceLayers()

            if button == Qt.LeftButton:
                modifiers = QApplication.keyboardModifiers()

                # todo: allow select modifiers to select more than one source layer
                if modifiers & Qt.ControlModifier:
                    newSelection = [s for s in oldSelection if s not in newSelection]
                elif modifiers & Qt.ShiftModifier:
                    for s in oldSelection:
                        if s not in newSelection:
                            newSelection.append(s)

                self.setSelectedSourceFiles(newSelection)

    def onTreeSelectionChanged(self, selected, deselected):
        self.mCanvas.setSelectedLayers(self.selectedSourceLayers())


    def selectedSourceBandNodes(self)->list:
        indexes = self.selectedIndexes()
        selectedFileNodes = self.mVRTRasterModel.indexes2nodes(indexes)
        return [n for n in selectedFileNodes if isinstance(n, VRTRasterInputSourceBandNode)]

    def selectedSourceLayers(self)->list:
        return [self.mSourceRasterModel.file2layer(f) for f in self.selectedSourceFiles()]

    def selectedSourceFiles(self)->list:
        files = []
        for node in self.selectedSourceBandNodes():
            assert isinstance(node, VRTRasterInputSourceBandNode)
            file = node.source()
            if isinstance(file, str):
                files.append(file)
        return files


    def setSelectedSourceFiles(self, newSelection):
        srcNodesAll = self.model().mRootNode.findChildNodes(
            VRTRasterInputSourceBandNode, recursive=True)

        nodeSelection = QItemSelection()
        # 1. select the nodes pointing to one of the source files
        for n in srcNodesAll:
            assert isinstance(n, VRTRasterInputSourceBandNode)
            uri = n.source()
            if uri in newSelection:
                idx = self.model().node2idx(n)
                nodeSelection.select(idx, idx)
        # v = self.blockSignals(True)
        self.select(nodeSelection, QItemSelectionModel.ClearAndSelect)
        # self.blockSignals(v)
        # self.model().select(self.model.node2idx(n), QItemSelectionModel.Select)


class VRTRasterTreeModel(TreeModel):
    def __init__(self, vrtRaster:VRTRaster, parent=None):
        assert isinstance(vrtRaster, VRTRaster)
        rootNode = VRTRasterNode(None, vrtRaster)
        super(VRTRasterTreeModel, self).__init__(parent, rootNode=rootNode)
        self.mVRTRaster = vrtRaster
        self.mColumnNames = ['Virtual Raster']
        self.mDropMode = 'NESTED_STACK'

    def setDropMode(self, mode):
        assert mode in ['NESTED_STACK', 'PURE_STACK']
        self.mDropMode = mode

    def setData(self, index, value, role):
        node = self.idx2node(index)
        col = index.column()

        if role == Qt.EditRole:
            if isinstance(node, VRTRasterBandNode) and col == 0:
                if len(value) > 0:
                    node.setName(value)
                    node.mVirtualBand.setName(value)
                    return True

        return False

    def srcFileIndices(self, srcFile)->list:
        """
        :param srcFile:
        :return:
        """
        srcFileNodes = self.mRootNode.findChildNodes(VRTRasterInputSourceBandNode, recursive=True)
        return self.nodes2indexes(srcFileNodes)

    def removeSources(self, sources):
        if isinstance(sources, set):
            sources = list(sources)
        assert isinstance(sources, list)
        for source in sources:
            self.mVRTRaster.removeInputSource(source)

    def removeNodes(self, nodes):

        for vBandNode in [n for n in nodes if isinstance(n, VRTRasterBandNode)]:
            self.mVRTRaster.removeVirtualBand(vBandNode.mVirtualBand)

        for vBandSrcNode in [n for n in nodes if isinstance(n, VRTRasterInputSourceBandNode)]:
            assert isinstance(vBandSrcNode, VRTRasterInputSourceBandNode)
            srcBand = vBandSrcNode.mSrc

            srcBand.virtualBand().removeSource(srcBand)

    def removeRows(self, row, count, parent):
        parentNode = self.idx2node(parent)

        if isinstance(parentNode, VRTRasterBandNode):
            # self.beginRemoveRows(parent, row, row+count-1)
            vBand = parentNode.mVirtualBand
            for n in parentNode.childNodes()[row:row + count]:
                vBand.removeSource(n.mSrc)
            # self.endRemoveRows()
            return True
        else:
            return False

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsDropEnabled

        node = self.idx2node(index)
        flags = super(VRTRasterTreeModel, self).flags(index)

        if isinstance(node, VRTRasterBandNode):
            flags |= Qt.ItemIsDropEnabled
            flags |= Qt.ItemIsEditable
        if isinstance(node, VRTRasterInputSourceBandNode):
            flags |= Qt.ItemIsDropEnabled
            flags |= Qt.ItemIsDragEnabled
        return flags



    def mimeTypes(self):
        # specifies the mime types handled by this model
        types = []
        types.append('text/uri-list')
        types.append(MDK_BANDLIST)
        return types

    def mimeData(self, indexes):
        indexes = sorted(indexes)
        nodes = [self.idx2node(i) for i in indexes]

        sourceBands = []

        for node in nodes:
            if isinstance(node, VRTRasterInputSourceBandNode):
                sourceBand = node.sourceBand()
                assert isinstance(sourceBand, VRTRasterInputSourceBand)
                sourceBands.append(sourceBand)

        sourceBands = list(OrderedDict.fromkeys(sourceBands))
        uriList = [sourceBand.mSource for sourceBand in sourceBands]
        uriList = list(OrderedDict.fromkeys(uriList))

        mimeData = QMimeData()

        if len(sourceBands) > 0:
            mimeData.setData(MDK_BANDLIST, pickle.dumps(sourceBands))

        # set text/uri-list
        if len(uriList) > 0:
            mimeData.setUrls([QUrl(p) for p in uriList])
            mimeData.setText('\n'.join(uriList))

        return mimeData

    def dropMimeData(self, mimeData, action, row, col, parentIndex):
        if action == Qt.IgnoreAction:
            return True

        assert isinstance(mimeData, QMimeData)
        # assert isinstance(action, QDropEvent)
        sourceBands = []

        if MDK_BANDLIST in mimeData.formats():
            dump = mimeData.data(MDK_BANDLIST)
            sourceBands = pickle.loads(dump)

        elif MDK_INDICES in mimeData.formats():
            dump = mimeData.data(MDK_INDICES)
            indices = pickle.loads(dump)
            s = ""

            if action == Qt.MoveAction:
                s = ""
        # drop files
        elif mimeData.hasUrls():
            for url in mimeData.urls():
                url = url2path(url)
                if url is not None:
                    sourceBands.extend(VRTRasterInputSourceBand.fromRasterLayer(url))

        if len(sourceBands) == 0:
            return False

        if self.mDropMode == 'NESTED_STACK':

            # re-order source bands by
            # 1. source file band index
            # 2. source file
            # Aim: create a nested list like
            #  [[file 1 band1, file 2 band1, file 3 band 92] <- source bands for the 1st virtual band,
            #   [file 1 band2, file 2 band2, file 3 band 93] <- source bands for the 2nd virtual band
            #  ]

            # step 1: temporary storage by source image path
            sourceImages = {}
            for b in sourceBands:
                assert isinstance(b, VRTRasterInputSourceBand)
                if not b.mSource in sourceImages.keys():
                    sourceImages[b.mSource] = []
                sourceImages[b.mSource].append(b)
            for p in sourceImages.keys():
                sourceImages[p] = sorted(sourceImages[p], key=lambda b: b.mBandIndex)

            if len(sourceImages) == 0:
                return True

            # step 2: create the nested list



            sourceBands = []
            while len(sourceImages) > 0:
                sourceBands.append([])

                for k in list(sourceImages.keys()):
                    sourceBands[-1].append(sourceImages[k].pop(0))
                    if len(sourceImages[k]) == 0:
                        del sourceImages[k]
                s = ""
        elif self.mDropMode == 'PURE_STACK':
            # pure stacking: each source band defines its own virtual band
            sourceBands = [[b] for b in sourceBands]
        else:
            raise NotImplementedError('Unknown DropMode: "{}"'.format(self.mDropMode))

        # ensure that we start with a VRTRasterBandNode
        parentNode = self.idx2node(parentIndex)
        if isinstance(parentNode, VRTRasterInputSourceBandNode):
            parentNode = parentNode.parentNode()
        elif isinstance(parentNode, VRTRasterNode):
            # 1. set the last VirtualBand as first input node
            vBand = VRTRasterBand()
            self.mVRTRaster.addVirtualBand(vBand)
            parentNode = self.mRootNode.findChildNodes(VRTRasterBandNode, recursive=False)[-1]

        assert isinstance(parentNode, VRTRasterBandNode)

        # this is the first virtual band to insert sources in
        vBand = parentNode.mVirtualBand
        assert isinstance(vBand, VRTRasterBand)
        if row < 0:
            row = 0

        # add the source bands to the VRT
        for bands in sourceBands:
            iSrc = row
            for src in bands:
                assert isinstance(src, VRTRasterInputSourceBand)
                if len(vBand) == 0 and re.search(r'Band \d+$', vBand.name(), re.I):
                    vBand.setName(src.name())
                vBand.insertSource(iSrc, src)
                iSrc += 1

            if bands != sourceBands[-1]:
                # add a new virtual band if the recent vBand is the last one
                if vBand == self.mVRTRaster.mBands[-1]:
                    self.mVRTRaster.addVirtualBand(VRTRasterBand())

                # go to next virtual band
                vBand = self.mVRTRaster.mBands[self.mVRTRaster.mBands.index(vBand) + 1]

        return True

    def supportedDragActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction


class MapToolIdentifySource(QgsMapToolIdentify):
    sigMapLayersIdentified = pyqtSignal(list)
    sigMapLayerIdentified = pyqtSignal(QgsMapLayer)
    sigEmptySelection = pyqtSignal()

    def __init__(self, canvas, layerType:QgsMapToolIdentify.Type):
        super(MapToolIdentifySource, self).__init__(canvas)
        self.mCanvas = canvas
        self.mLayerType = layerType
        self.setCursor(Qt.CrossCursor)

    def canvasPressEvent(self, e):
        pos = self.toMapCoordinates(e.pos())
        results = self.identify(QgsGeometry.fromWkt(pos.asWkt()), QgsMapToolIdentify.TopDownAll, self.mLayerType)
        if self.mLayerType == QgsMapToolIdentify.AllLayers:
            layers = [r.mLayer for r in results if isinstance(r.mLayer, QgsMapLayer)]
        elif self.mLayerType == QgsMapToolIdentify.VectorLayer:
            layers = [r.mLayer for r in results if isinstance(r.mLayer, QgsVectorLayer)]
        elif self.mLayerType == QgsMapToolIdentify.RasterLayer:
            layers = [r.mLayer for r in results if isinstance(r.mLayer, QgsRasterLayer)]

        if len(layers) > 0:
            self.sigMapLayerIdentified.emit(layers[0])
            self.sigMapLayersIdentified.emit(layers)
        else:
            self.sigEmptySelection.emit()
    def canvasReleaseEvent(self, e):
        pass

def url2path(url):
    assert isinstance(url, QUrl)
    if url.isValid():
        path = url.path()
        if url.isLocalFile() and \
                not os.path.isfile(path) and \
                        re.search('^/[^/].*:', path) is not None:
            # remove leading '/'
            path = path[1:]
        if os.path.exists(path):
            return path

    return None


class AboutWidget(QDialog, loadUi('about.ui')):
    def __init__(self, parent=None):
        super(AboutWidget, self).__init__(parent)
        self.setupUi(self)
        from vrtbuilder import VERSION
        self.labelVersion.setText('Version {}'.format(VERSION))


class VRTBuilderWidget(QFrame, loadUi('vrtbuilder.ui')):
    sigRasterCreated = pyqtSignal(str)

    def __init__(self, parent=None):
        super(VRTBuilderWidget, self).__init__(parent)
        self.setupUi(self)
        # self.webView.setUrl(QUrl('help.html'))
        title = self.windowTitle()
        self.setWindowIcon(QIcon(':/vrtbuilder/mActionNewVirtualLayer.svg'))
        from vrtbuilder import VERSION
        if VERSION not in title:
            title = '{} {}'.format(title, VERSION)
            self.setWindowTitle(title)

        self.mMapCanvases = []
        self.mMapCanvases.append(self.previewMap)

        jp = os.path.join
        dn = os.path.dirname



        #self.tabWidgetSettings.removeTab(2)
        thisDir = dn(__file__)
        pathHTML = [jp(thisDir, '../doc/build/html/index.html'),
                    jp(thisDir, '../help/index.html')]

        pathHTML = [p for p in pathHTML if os.path.exists(p)]
        if len(pathHTML) > 0:
            self.tabHelp.setVisible(True)

            pathHTML = pathHTML[0]
            #print(pathHTML)
            self.webView.load(QUrl.fromLocalFile(QFileInfo(pathHTML).absoluteFilePath()))

        else:
            self.tabHelp.setVisible(False)
            info = 'Unable to find help index.html'
            QgsApplication.instance().messageLog().logMessage(info)

        self.mSourceFileModel = SourceRasterModel(parent=self.treeViewSourceFiles)
        self.mSourceFileModel.sigSourcesRemoved.connect(self.buildButtonMenus)
        self.mSourceFileModel.sigSourcesAdded.connect(self.buildButtonMenus)

        self.mSourceFileProxyModel = SourceRasterFilterModel()
        self.mSourceFileProxyModel.setSourceModel(self.mSourceFileModel)

        self.tbSourceFileFilter.textChanged.connect(self.onSourceFileFilterChanged)
        self.cbSourceFileFilterRegex.clicked.connect(
            lambda: self.onSourceFileFilterChanged(self.tbSourceFileFilter.text()))
        # self.treeViewSourceFiles.setModel(self.sourceFileModel)

        assert isinstance(self.treeViewSourceFiles, QTreeView)
        self.treeViewSourceFiles.setModel(self.mSourceFileProxyModel)
        self.treeViewSourceFiles.setDragEnabled(True)
        self.treeViewSourceFiles.setAcceptDrops(True)
        self.treeViewSourceFiles.setDropIndicatorShown(True)




        self.cbInMemoryOutput.clicked.connect(self.onInMemoryOutputTriggered)

        def onDragEnter(event):
            assert isinstance(event, QDragEnterEvent)
            supported = self.mSourceFileModel.mimeTypes()
            for f in event.mimeData().formats():
                if f in supported:
                    event.acceptProposedAction()

        self.treeViewSourceFiles.dragEnterEvent = onDragEnter
        selectionModel = self.treeViewSourceFiles.selectionModel()
        self.actionRemoveSourceFiles.setEnabled(False)
        selectionModel.selectionChanged.connect(lambda selected, deselected : self.actionRemoveSourceFiles.setEnabled(selected.count() > 0))


        self.tbNoData.setValidator(QDoubleValidator())

        filter = 'GDAL Virtual Raster (*.vrt);;GeoTIFF (*.tiff *.tif);;ENVI (*.bsq *.bil *.bip)'

        self.mQgsFileWidget.setFilter(filter)
        self.mQgsFileWidget.setStorageMode(QgsFileWidget.SaveFile)
        self.mQgsFileWidget.fileChanged.connect(self.onOutputPathChanged)

        self.buttonBox.button(QDialogButtonBox.Save).clicked.connect(self.saveFile)
        self.buttonBox.button(QDialogButtonBox.Close).clicked.connect(self.close)
        self.mVRTRaster = VRTRaster()

        #self.vrtRaster.sigSourceBandInserted.connect(self.resetMap)
        #self.vrtRaster.sigSourceRasterAdded.connect(self.resetMap)

        assert isinstance(self.previewMap, VRTRasterPreviewMapCanvas)


        self.mVRTRaster.sigCrsChanged.connect(self.updateSummary)
        #self.mVRTRaster.sigSourceBandInserted.connect(self.onVRTSourceBandAdded)
        self.mVRTRaster.sigSourceBandInserted.connect(self.updateSummary)
        self.mVRTRaster.sigSourceBandRemoved.connect(self.updateSummary)
        self.mVRTRaster.sigBandInserted.connect(self.updateSummary)
        self.mVRTRaster.sigBandRemoved.connect(self.updateSummary)
        self.mVRTRaster.sigExtentChanged.connect(self.updateSummary)
        self.mVRTRaster.sigResolutionChanged.connect(self.updateSummary)
        self.previewMap.setVRTRaster(self.mVRTRaster)
        self.mVRTRasterTreeModel = VRTRasterTreeModel(self.mVRTRaster, parent=self.treeViewVRT)
        self.btnStackFiles.toggled.connect(lambda isChecked:
                                           self.mVRTRasterTreeModel.setDropMode('PURE_STACK')
                                           if isChecked
                                           else self.mVRTRasterTreeModel.setDropMode(('NESTED_STACK')))

        self.treeViewVRT.setModel(self.mVRTRasterTreeModel)

        self.vrtTreeSelectionModel = VRTSelectionModel(self.treeViewVRT.model(), self.mSourceFileModel, self.previewMap)
        self.vrtTreeSelectionModel.selectionChanged.connect(self.onVRTSelectionChanged)

        self.treeViewVRT.setSelectionModel(self.vrtTreeSelectionModel)

        # 2. expand the parent nodes
        self.treeViewVRT.setAutoExpandDelay(50)
        self.treeViewVRT.setDragEnabled(True)
        self.treeViewVRT.contextMenuEvent = self.vrtTreeViewContextMenuEvent


        self.initActions()


        self.mMapTools = []


        self.restoreLastSettings()
        self.validateInputs()
        self.resetMap()
            
    def initActions(self):



        self.btnCopyResolution.setDefaultAction(self.actionCopyResolution)
        self.btnCopyExtent.setDefaultAction(self.actionCopyExtent)
        self.bntCopyGrid.setDefaultAction(self.actionCopyGrid)
        self.btnAlignGrid.setDefaultAction(self.actionAlignGrid)
        self.bntDrawExtent.setDefaultAction(self.actionSelectSpatialExtent)

        self.actionCopyResolution.triggered.connect(lambda : self.activateMapTool('COPY_RESOLUTION'))
        self.actionCopyExtent.triggered.connect(lambda: self.activateMapTool('COPY_EXTENT'))
        self.actionCopyGrid.triggered.connect(lambda: self.activateMapTool('COPY_GRID'))
        self.actionAlignGrid.triggered.connect(lambda: self.activateMapTool('ALIGN_GRID'))
        self.actionSelectSpatialExtent.triggered.connect(lambda : self.activateMapTool('SELECT_EXTENT'))
        self.buildButtonMenus() #adds QMenus to each button


        self.onInMemoryOutputTriggered(False)
        reg = QRegExp(r"^\D[^ ]*\.vrt$")
        self.lineEditInMemory.setValidator(QRegExpValidator(reg))

        #
        for tb in [self.tbBoundsXMin, self.tbBoundsXMax, self.tbBoundsYMin, self.tbBoundsYMax]:
            #.textEdited is emited on "manual" changed only
            tb.textEdited.connect(lambda : self.calculateGrid(changedExtent=True))
            tb.setValidator(QDoubleValidator(-999999999999999999999.0, 999999999999999999999.0, 20))

        def onResolutionValueChanged(value):
            sender = QApplication.instance().sender()
            if sender == self.sbResolutionX:
                if self.cbLinkResolutionXY.isChecked():
                    self.sbResolutionY.setValue(value)
                    return
            if sender == self.sbResolutionY:
                pass

            self.calculateGrid(changedResolution=True)
        self.sbResolutionX.valueChanged[float].connect(onResolutionValueChanged)
        self.sbResolutionY.valueChanged[float].connect(onResolutionValueChanged)

        self.sbRasterWidth.valueChanged.connect(lambda : self.calculateGrid(changedSize=True))
        self.sbRasterHeight.valueChanged.connect(lambda : self.calculateGrid(changedSize=True))

        self.cbResampling.clear()
        self.cbResampling.setModel(RESAMPLE_ALGS)


        def onAddSourceFiles(*args):

            files, filer = QFileDialog.getOpenFileNames(self, "Open raster images", directory='')
            if len(files) > 0:
                self.addSourceFiles(files)

        self.btnAddFromRegistry.clicked.connect(self.loadSrcFromMapLayerRegistry)
        self.btnAddSrcFiles.clicked.connect(onAddSourceFiles)
        self.btnRemoveSrcFiles.setDefaultAction(self.actionRemoveSourceFiles)

        def onRemoveSelectedSourceFiles():
            sm = self.treeViewSourceFiles.selectionModel()
            m = self.treeViewSourceFiles.model()
            assert isinstance(m, SourceRasterFilterModel)

            to_remove = []
            rows = sm.selectedRows()
            for rowIdx in rows:
                node = m.data(rowIdx, Qt.UserRole)
                if isinstance(node, SourceRasterFileNode):
                    to_remove.append(node.mPath)
                elif isinstance(node, TreeNode) and isinstance(node.parentNode(), SourceRasterFileNode):
                    to_remove.append(node.parentNode().mPath)
                else:
                    s = ""
            if len(to_remove) > 0:
                self.mSourceFileModel.removeFiles(to_remove)

            # self.sourceFileModel.removeFiles(    [n.mPath for n in self.selectedSourceFileNodes()]

        self.actionRemoveSourceFiles.triggered.connect(onRemoveSelectedSourceFiles)

        self.cbResampling.currentIndexChanged.connect(lambda:
                                                      self.mVRTRaster.setResamplingAlg(
                                                          self.cbResampling.currentData().mValue
                                                      ))
        self.mVRTRaster.sigResamplingAlgChanged[int].connect(lambda alg:
                                                            self.cbResampling.setCurrentIndex(
                                                                RESAMPLE_ALGS.optionValues().index(alg)))

        self.btnExpandAllVRT.clicked.connect(lambda: self.expandSelectedNodes(self.treeViewVRT, True))
        self.btnCollapseAllVRT.clicked.connect(lambda: self.expandSelectedNodes(self.treeViewVRT, False))

        self.btnExpandAllSrc.clicked.connect(lambda: self.expandSelectedNodes(self.treeViewSourceFiles, True))
        self.btnCollapseAllSrc.clicked.connect(lambda: self.expandSelectedNodes(self.treeViewSourceFiles, False))

        self.btnAddVirtualBand.clicked.connect(
            lambda: self.mVRTRaster.addVirtualBand(VRTRasterBand(name='Band {}'.format(len(self.mVRTRaster) + 1))))
        self.btnRemoveVirtualBands.clicked.connect(lambda: self.mVRTRasterTreeModel.removeNodes(
            self.mVRTRasterTreeModel.indexes2nodes(self.treeViewVRT.selectedIndexes())
        ))

        self.btnLoadVRT.setDefaultAction(self.actionLoadVRT)

        self.btnAbout.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        self.btnAbout.clicked.connect(lambda: AboutWidget(self).exec_())

        self.crsSelectionWidget.setMessage('Set VRT CRS')
        self.crsSelectionWidget.crsChanged.connect(self.mVRTRaster.setCrs)

        #map tools

        self.actionPan.triggered.connect(lambda: self.activateMapTool('PAN'))
        self.actionZoomIn.triggered.connect(lambda: self.activateMapTool('ZOOM_IN'))
        self.actionZoomOut.triggered.connect(lambda: self.activateMapTool('ZOOM_OUT'))
        self.actionSelectSourceLayer.triggered.connect(lambda: self.activateMapTool('IDENTIFY_SOURCE'))


        self.btnZoomIn.setDefaultAction(self.actionZoomIn)
        self.btnZoomOut.setDefaultAction(self.actionZoomOut)
        self.btnPan.setDefaultAction(self.actionPan)
        self.btnZoomExtent.clicked.connect(self.previewMap.reset)

        self.btnSelectFeature.setDefaultAction(self.actionSelectSourceLayer)



        def onLoadVRT(*args):
            fn, filer = QFileDialog.getOpenFileName(self, "Open VRT file", filter='GDAL Virtual Raster (*.vrt)',
                                                    directory='')

            if len(fn) > 0:
                self.loadVRT(fn)

        self.actionLoadVRT.triggered.connect(onLoadVRT)


        # extents
        self.cbBoundsFromSourceFiles.clicked.connect(self.onUseAutomaticExtent)
        self.cbBoundsFromSourceFiles.setChecked(True)
        self.onUseAutomaticExtent(True)


    def onInMemoryOutputTriggered(self, b):
        if b:
            self.mQgsFileWidget.setVisible(False)
            self.frameInMemoryPath.setVisible(True)

        else:
            self.mQgsFileWidget.setVisible(True)
            self.frameInMemoryPath.setVisible(False)

        s = ""


    def loadVRT(self, path):
        if path is not None and os.path.isfile(path):
            self.mVRTRaster.loadVRT(path)


    def knownSpatialSources(self)->list:
        pass

    def knownRasterSources(self)->list:
        pass

    def knownVectorSources(self)->list:
        pass

    def mapCanvases(self)->list:
        """
        Returns a list of QgsMapCanvases to interact with
        :return: [list-of-QgsMapCanvases]
        """
        return self.mMapCanvases[:]

    def registerMapCanvas(self, mapCanvas:QgsMapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)
        if mapCanvas not in self.mMapCanvases:
            self.mMapCanvases.append(mapCanvas)

    def activateMapTool(self, name:str, deactivateAfter:bool=False):
        """
        Activates a QgsMapTools for all registered QgsMapCanvases
        :param name: str,
        """


        self.mMapTools.clear()

        for canvas in self.mapCanvases():
            mapTool = None
            assert isinstance(canvas, QgsMapCanvas)

            if name == 'ZOOM_IN':
                mapTool = QgsMapToolZoom(canvas, False)
            elif name == 'ZOOM_OUT':
                mapTool = QgsMapToolZoom(canvas, True)
            elif name == 'PAN':
                mapTool = QgsMapToolPan(canvas)

            elif name == 'IDENTIFY_SOURCE':
                def onLayersSelected(layers: list):
                    sources = [l.source() for l in layers]
                    self.vrtTreeSelectionModel.setSelectedSourceFiles(sources)

                mapTool = MapToolIdentifySource(canvas, QgsMapToolIdentify.RasterLayer)
                mapTool.sigMapLayersIdentified.connect(onLayersSelected)
                mapTool.sigEmptySelection.connect(lambda : onLayersSelected([]))

            elif name == 'SELECT_EXTENT':

                mapTool = SpatialExtentMapTool(canvas)
                mapTool.sigSpatialExtentSelected.connect(self.setExtent)

            elif name == 'COPY_RESOLUTION':
                mapTool = MapToolIdentifySource(canvas, QgsMapToolIdentify.RasterLayer)

                def onLayerSelected(lyr):
                    assert isinstance(lyr, QgsRasterLayer)
                    res = QSizeF(lyr.rasterUnitsPerPixelX(), lyr.rasterUnitsPerPixelY())

                    self.mVRTRaster.setResolution(res, crs = lyr.crs())

                mapTool.sigMapLayerIdentified.connect(onLayerSelected)

            elif name == 'COPY_EXTENT':
                mapTool = MapToolIdentifySource(canvas, QgsMapToolIdentify.AllLayers)
                mapTool.sigMapLayerIdentified.connect(lambda lyr: self.mVRTRaster.setExtent(lyr.extent(), crs=lyr.crs()))

            elif name == 'COPY_GRID':
                mapTool = MapToolIdentifySource(canvas, QgsMapToolIdentify.RasterLayer)
                mapTool.sigMapLayerIdentified.connect(lambda lyr: self.mVRTRaster.alignToRasterGrid(lyr, True))

            elif name == 'ALIGN_GRID':
                mapTool = MapToolIdentifySource(canvas, QgsMapToolIdentify.RasterLayer)
                mapTool.sigMapLayerIdentified.connect(lambda lyr: self.mVRTRaster.alignToRasterGrid(lyr, False))
            else:
                raise NotImplementedError('Unknowm maptool key "{}"'.format(name))

            if isinstance(mapTool, QgsMapTool):
                canvas.setMapTool(mapTool)
                self.mMapTools.append(mapTool)


    def onSourceFileFilterChanged(self, text):

        useRegex = self.cbSourceFileFilterRegex.isChecked()
        if useRegex:
            self.mSourceFileProxyModel.setFilterRegExp(text)
        else:
            self.mSourceFileProxyModel.setFilterWildcard(text)

        pass

    def setExtent(self, spatialExtent:SpatialExtent):
        """
        Sets the boundaries of destination raster image
        :param bbox: QgsRectangle
        :param crs: Target QgsCoordinateReferenceSystem. Defaults to the VRT crs.
        """
        assert isinstance(spatialExtent, SpatialExtent)
        
        if not isinstance(self.mVRTRaster.crs(), QgsCoordinateReferenceSystem):
            self.mVRTRaster.setCrs(spatialExtent.crs())
        spatialExtent = spatialExtent.toCrs(self.mVRTRaster.crs())
        self.mVRTRaster.setExtent(spatialExtent)

        self.validateInputs()

    def setBoundsFromSource(self, source):
        """Copies the spatial extent from a given raster or vector source"""
        lyr = toMapLayer(source)
        if isinstance(lyr, QgsMapLayer):
            spatialExtent = SpatialExtent.fromLayer(lyr)
            if isinstance(spatialExtent, SpatialExtent):
                self.setExtent(spatialExtent)

    def setResolutionFromSource(self, source):
        """Copies the pixel resolution from a QgsRasterLayer"""
        lyr = toRasterLayer(source)
        if isinstance(lyr, QgsRasterLayer):
            self.mVRTRaster.setResolution(resolution(lyr), crs=lyr.crs())

    def setGridFrom(self, source):
        """
        Copies the raster grid (CRS, extent, pixel size) from a raster source
        :param source: any type
        """
        lyr = toRasterLayer(source)
        if isinstance(lyr, QgsRasterLayer):
            crs = lyr.crs()
            res = resolution(lyr)
            ext = lyr.extent()
            self.mVRTRaster.setCrs(crs)
            self.mVRTRaster.setResolution(res)
            refPoint = QgsPointXY(ext.xMinimum(), ext.yMaximum())
            self.mVRTRaster.setExtent(ext, referenceGrid=refPoint)


    def buildButtonMenus(self, *args):


        # refresh menu to select image bounds & image resolutions
        menuCopyResolution = QMenu()
        menuCopyExtent = QMenu()
        menuCopyGrid = QMenu()
        menuAlignGrid = QMenu()

        import qgis.utils
        if isinstance(qgis.utils.iface, QgisInterface) and \
             isinstance(qgis.utils.iface.mapCanvas(), QgsMapCanvas):
            a = menuCopyExtent.addAction('QGIS MapCanvas')
            a.setToolTip('Use spatial extent of QGIS map canvas.')
            a.triggered.connect(lambda: self.setExtent(SpatialExtent.fromMapCanvas(qgis.utils.iface.mapCanvas())))

        menuCopyExtent.addAction(self.actionSelectSpatialExtent)

        vectorLayerSources = []
        rasterLayerSources = []
        handledSources = set()

        for file in self.mSourceFileModel.rasterSources():
            rasterLayerSources.append(file)
            handledSources.add(file)

        for layer in QgsProject.instance().mapLayers().values():
            if layer.source() in handledSources:
                continue

            handledSources.add(layer.source())

            if isinstance(layer, QgsRasterLayer):
                rasterLayerSources.append(layer)
            elif isinstance(layer, QgsVectorLayer):
                vectorLayerSources.append(layer)



        for source in rasterLayerSources:
            bn = sourceBaseName(source)
            if isinstance(source, str):
                file = source
                icon = QIcon(r':/images/themes/default/mIconRaster.svg')
            elif isinstance(source, QgsRasterLayer):
                icon = sourceIcon(source)
                file = source.source()


            a = menuCopyExtent.addAction(bn)
            a.setToolTip('Use spatial extent of {}. (Extent will be converted into the current CRS.)'.format(file))
            a.triggered.connect(lambda *args, src=source: self.setBoundsFromSource(src))
            a.setIcon(icon)
            
            a = menuCopyResolution.addAction(bn)
            a.setToolTip('Use resolution of {}.'.format(file))
            a.triggered.connect(lambda *args, src=source: self.setResolutionFromSource(src))
            a.setIcon(icon)
            
            a = menuCopyGrid.addAction(bn)
            a.setToolTip('Use pixel grid of {}'.format(file))
            a.triggered.connect(lambda *args, src=source: self.setGridFrom(src))
            a.setIcon(icon)
            
            a = menuAlignGrid.addAction(bn)
            a.setToolTip('Align to pixel grid of {}'.format(file))
            a.triggered.connect(lambda *args, src=source: self.mVRTRaster.alignToRasterGrid(src))
            a.setIcon(icon)
        
        if len(vectorLayerSources) > 0:
            menuCopyExtent.addSeparator()
            
            for source in vectorLayerSources:
                if isinstance(source, QgsVectorLayer):
                    icon = sourceIcon(source)
                    bn = sourceBaseName(source)
                    a = menuCopyExtent.addAction(bn)
                    a.setToolTip('Use spatial extent of {}'.format(layer.source()))
                    a.triggered.connect(lambda *args, src=source: self.setBoundsFromSource(src))
                    a.setIcon(icon)
        
        self.btnCopyResolution.setMenu(menuCopyResolution)
        self.btnCopyExtent.setMenu(menuCopyExtent)
        self.bntCopyGrid.setMenu(menuCopyGrid)
        self.btnAlignGrid.setMenu(menuAlignGrid)

    def onUseAutomaticExtent(self, auto:bool):

        for a in [self.actionSelectSpatialExtent, self.actionCopyExtent, self.actionCopyGrid]:
            a.setDisabled(auto)

        for w in [self.tbBoundsXMin, self.tbBoundsXMax, self.tbBoundsYMin, self.tbBoundsYMax, self.sbRasterWidth, self.sbRasterHeight]:
            w.setDisabled(auto)



    def calculateGrid(self, changedResolution:bool=False, changedExtent:bool=False, changedCrs:bool=False, changedSize:bool=False):

        n = sum([changedResolution, changedExtent, changedCrs, changedSize])
        assert n <= 1, 'only one aspect should be changed on same time manually'

        if changedResolution:
            #recalculate the grid with new pixel resolution
            res = QSizeF(self.sbResolutionX.value(), self.sbResolutionY.value())
            if res.width() > 0  and res.height() > 0:
                self.mVRTRaster.setResolution(res)
            return

        if changedSize:
            #recalculate grid with new raster size
            width = max(self.sbRasterWidth.value(),1)
            height = max(self.sbRasterHeight.value(),1)
            self.mVRTRaster.setSize(QSize(width, height))
            pass

        if changedCrs:
            pass

        if changedExtent:
            #recalculate with new extent

            if self.cbBoundsFromSourceFiles.isChecked():
                #derive from source files
                extent = self.mVRTRaster.fullSourceRasterExtent()
                if isinstance(extent, QgsRectangle):
                    self.mVRTRaster.setExtent(extent)

            else:
                values = [tb.text() for tb in [self.tbBoundsXMin, self.tbBoundsYMin, self.tbBoundsXMax, self.tbBoundsYMax]]
                if '' not in values:
                    S = ""
                    values = [float(v) for v in values]
                    rectangle = QgsRectangle(*values)
                    if rectangle.width() > 0 and rectangle.height() > 0:
                        self.mVRTRaster.setExtent(rectangle)

        self.validateInputs()

    def validateInputs(self, *args):

        isValid = len(self.mVRTRaster) > 0
        if not self.cbBoundsFromSourceFiles.isEnabled():
            for tb in [self.tbBoundsXMin, self.tbBoundsXMax, self.tbBoundsYMin, self.tbBoundsYMax]:
                state, _, _ = tb.validator().validate(tb.text(), 0)
                isValid &= state == QValidator.Acceptable
            if isValid:
                isValid &= float(self.tbBoundsXMin.text()) < float(self.tbBoundsXMax.text())
                isValid &= float(self.tbBoundsYMin.text()) < float(self.tbBoundsYMax.text())

        self.buttonBox.button(QDialogButtonBox.Save).setEnabled(isValid)


    def restoreDefaultSettings(self):
        self.cbAddToMap.setChecked(True)
        self.cbCRSFromInputData.setChecked(True)
        from os.path import expanduser
        self.tbOutputPath.setText(os.path.join(expanduser('~'), 'output.vrt'))
        self.cbBoundsFromSourceFiles.setChecked(True)
        self.saveSettings()

    def saveSettings(self):
        from vrtbuilder.utils import settings
        settings = settings()
        assert isinstance(settings, QSettings)
        settings.setValue('PATH_SAVE', self.mQgsFileWidget.filePath())

        settings.setValue('AUTOMATIC_BOUNDS', self.cbBoundsFromSourceFiles.isChecked())

    def restoreLastSettings(self):
        from vrtbuilder.utils import settings
        settings = settings()
        assert isinstance(settings, QSettings)
        from os.path import expanduser
        self.mQgsFileWidget.setFilePath(settings.value('PATH_SAVE', os.path.join(expanduser('~'), 'output.vrt')))

        self.cbBoundsFromSourceFiles.setChecked(bool(settings.value('AUTOMATIC_BOUNDS', True)))
        s = ""

    def resetMap(self, *args):

        lyrs = []

        LUT = dict()
        for layer in self.mSourceFileModel.rasterLayers():
            LUT[layer.source()] = layer

        for file in self.mVRTRaster.sourceRaster():
            if file in LUT.keys():
                lyr = LUT[file]
                if lyr not in lyrs:
                    lyrs.append(lyr)

        if lyrs != self.previewMap.layers():
            self.previewMap.setLayers(lyrs)


    def onVRTSelectionChanged(self, selected, deselected):
        self.btnRemoveVirtualBands.setEnabled(selected.count() > 0)
        # 2. expand the parent nodes
        model = self.mVRTRasterTreeModel
        nodes = [model.idx2node(idx) for idx in selected.indexes()]
        selected = set([model.node2idx(n.parentNode()) for n in nodes if isinstance(n, VRTRasterInputSourceBandNode)])
        for idx in selected:
            self.treeViewVRT.expand(idx)

    def loadSrcFromMapLayerRegistry(self):
        #reg = QgsMapLayerRegistry.instance()

        sources = set(lyr.source() for lyr in list(QgsProject.instance().mapLayers().values()) if isinstance(lyr, QgsRasterLayer))
        sources = list(sources)
        sources = sorted(sources, key = lambda s : os.path.basename(s))

        self.mSourceFileModel.addSources(sources)

    def expandNodes(self, treeView, nodes, expand):
        assert isinstance(treeView, QTreeView)
        model = treeView.model()
        assert isinstance(model, TreeModel)
        for node in nodes:
            treeView.setExpanded(model.node2idx(node))

    def expandSelectedNodes(self, treeView, expand):
        assert isinstance(treeView, QTreeView)

        indices = treeView.selectedIndexes()
        if len(indices) == 0:
            treeView.selectAll()
            indices += treeView.selectedIndexes()
            treeView.clearSelection()
        for idx in indices:
            treeView.setExpanded(idx, expand)

    def _saveFileCallback(self, percent, x, path):
        self.progressBar.setValue(int(percent * 100))
        if x != '':
            self.tbProgress == x

    def saveFile(self):

        dsDst = None
        inMemory = self.cbInMemoryOutput.isChecked()
        if inMemory:
            path = '/vsimem/'+self.lineEditInMemory.text()
        else:
            path = self.mQgsFileWidget.filePath()
        ext = os.path.splitext(path)[-1]

        saveBinary = ext != '.vrt'
        if saveBinary:
            pathVrt = path + '.vrt'
            self.mVRTRaster.saveVRT(pathVrt)

            ext = ext.lower()
            if ext in LUT_FILEXTENSIONS.keys():
                drv = LUT_FILEXTENSIONS[ext]
            else:
                drv = gdal.GetDriverByName('VRT')

            co = []
            if drv == 'ENVI':
                if ext in ['.bsq', '.bip', '.bil']:
                    co.append('INTERLEAVE={}'.format(ext[1:].upper()))

            options = gdal.TranslateOptions(format=str(drv), creationOptions=co,
                                            callback=self._saveFileCallback, callback_data=path)

            self.tbProgress.setText('Save {}...'.format(path))
            dsDst = gdal.Translate(path, pathVrt, options=options)
            self.fullProgress()

        else:
            pathVrt = path
            self.tbProgress.setText('Save {}...'.format(pathVrt))
            dsDst = self.mVRTRaster.saveVRT(pathVrt)
            self.tbProgress.setText('{} saved'.format(pathVrt))
            self.fullProgress()
        if isinstance(dsDst, gdal.Dataset):
            self.tbProgress.setText('{} saved'.format(path))
        else:
            self.tbProgress.setText('Failed to save {}!'.format(path))

        dsDst = None
        if self.cbAddToMap.isChecked():
            self.sigRasterCreated.emit(path)
            #lyr = QgsRasterLayer(path)
            #self.tmpLyr = lyr
            #self.addSourceFile(path)
            #QgsProject.instance().addMapLayer(lyr)


        self.saveSettings()

    def fullProgress(self):
        self.progressBar.setValue(100)
        QTimer.singleShot(1000, lambda : self.progressBar.setValue(0))

    def onOutputPathChanged(self, path):
        assert isinstance(self.buttonBox, QDialogButtonBox)
        isEnabled = False
        if len(path) > 0:
            ext = os.path.splitext(path)[-1].lower()
            isEnabled = ext in ['.vrt', '.bsq', '.tif', '.tiff']

        self.buttonBox.button(QDialogButtonBox.Save).setEnabled(isEnabled)

    def onSrcModelSelectionChanged(self, selected, deselected):

        self.btnRemoveSrcFiles.setEnabled(len(self.selectedSourceFileNodes()) > 0)
        s = ""

    def addSourceFile(self, file):

        self.addSourceFiles([file])

    def addSourceFiles(self, files):
        """
        Adds a list of source files to the source file list.
        :param files: list-of-file-paths
        """
        self.mSourceFileModel.addSources(files)



    def updateSummary(self):
        """
        Updates (almost) all information visible to the user
        """
        self.tbSourceFileCount.setText('{}'.format(len(self.mVRTRaster.sourceRaster())))
        self.tbVRTBandCount.setText('{}'.format(len(self.mVRTRaster)))
        assert isinstance(self.previewMap, VRTRasterPreviewMapCanvas)
        crs = self.mVRTRaster.crs()
        if isinstance(crs, QgsCoordinateReferenceSystem):
            if crs != self.crsSelectionWidget.crs():
                b = self.crsSelectionWidget.blockSignals(True)
                self.crsSelectionWidget.setCrs(crs)
                self.crsSelectionWidget.blockSignals(b)

            unitString = QgsUnitTypes.toAbbreviatedString(crs.mapUnits())
            self.sbResolutionX.setSuffix(unitString)
            self.sbResolutionY.setSuffix(unitString)


            if crs.mapUnits() in [QgsUnitTypes.DistanceDegrees]:
                self.sbResolutionX.setDecimals(10)
                self.sbResolutionY.setDecimals(10)
            else:
                self.sbResolutionX.setDecimals(4)
                self.sbResolutionY.setDecimals(4)

        extent = self.mVRTRaster.extent()
        if isinstance(extent, QgsRectangle):
            self.tbBoundsXMin.setText('{}'.format(extent.xMinimum()))
            self.tbBoundsXMax.setText('{}'.format(extent.xMaximum()))
            self.tbBoundsYMin.setText('{}'.format(extent.yMinimum()))
            self.tbBoundsYMax.setText('{}'.format(extent.yMaximum()))


        res = self.mVRTRaster.resolution()
        if isinstance(res, QSizeF):
            self.sbResolutionX.setValue(res.width())
            self.sbResolutionY.setValue(res.height())

        size = self.mVRTRaster.size()
        if isinstance(size, QSize):
            self.sbRasterWidth.setValue(size.width())
            self.sbRasterHeight.setValue(size.height())


        self.resetMap()

    def vrtTreeViewContextMenuEvent(self, event):

        idx = self.treeViewVRT.indexAt(event.pos())
        if not idx.isValid():
            pass

        selectedNodes = self.mVRTRasterTreeModel.indexes2nodes(self.treeViewVRT.selectedIndexes())
        menu = QMenu(self.treeViewVRT)
        a = menu.addAction('Remove bands')
        a.setToolTip('Remove selected nodes')
        a.triggered.connect(lambda: self.mVRTRasterTreeModel.removeNodes(selectedNodes))

        srcFiles = set()
        for n in selectedNodes:
            if isinstance(n, VRTRasterInputSourceBandNode):
                srcFiles.add(n.sourceBand().mSource)

        if len(srcFiles) > 0:
            a = menu.addAction('Remove sources')
            a.setToolTip('Remove all bands from selected source files.')
            a.triggered.connect(lambda: self.mVRTRasterTreeModel.removeSources(srcFiles))

        menu.exec_(self.treeViewVRT.viewport().mapToGlobal(event.pos()))
        """
        if (menu & & menu->actions().count() != 0 )
        menu->exec (mapToGlobal(event->pos() ) );
        delete
        menu;
        """

    def mapReset(self):

        self.previewMap.refresh()


if __name__ == '__main__':
    app = QApplication([])
    w = AboutWidget()
    w.show()
    app.exec_()
