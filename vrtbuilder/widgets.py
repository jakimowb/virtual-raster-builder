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

from collections import OrderedDict
import pickle
import webbrowser
import pathlib
import os
import typing
import re
import enum
from .externals.qps.maptools import SpatialExtentMapTool
from .externals.qps.models import TreeModel, TreeNode, TreeView
from osgeo import gdal
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import QgsRasterLayer, QgsMapLayer, QgsVectorLayer, \
    QgsCoordinateReferenceSystem, QgsUnitTypes, QgsRectangle, QgsCoordinateTransform, \
    QgsPointXY, QgsWkbTypes, QgsProject, \
    QgsGeometry, QgsMapLayerStore
from qgis.gui import QgsMapCanvas, QgsFileWidget, QgsRubberBand, QgisInterface, \
    QgsMapToolIdentify, QgsMapTool, QgsMapToolPan, QgsMapToolZoom, QgsMapToolEmitPoint, \
    QgsStatusBar

from vrtbuilder import DIR_UI, __version__, URL_REPOSITORY, URL_ISSUETRACKER, URL_HOMEPAGE
from .virtualrasters import VRTRaster, VRTRasterBand, VRTRasterInputSourceBand, RESAMPLE_ALGS, resolution
from .externals.qps.utils import loadUi, SpatialExtent, SpatialPoint, qgsRasterLayer, qgsRasterLayers, qgsMapLayer
from .externals.qps.maptools import MapTools


def settings() -> QSettings:
    return QSettings('HU-Berlin', 'Virtual Raster Builder')


LUT_FILEXTENSIONS = {}

MDK_BANDLIST = 'hub.vrtbuilder/bandlist'
MDK_INDICES = 'hub.vrtbuilder/vrt.indices'

for i in range(gdal.GetDriverCount()):
    drv = gdal.GetDriver(i)
    assert isinstance(drv, gdal.Driver)

    extensions = drv.GetMetadataItem(gdal.DMD_EXTENSIONS)
    if extensions is None:
        extensions = ''

    extensions = extensions.split(' ')
    extensions = [e for e in extensions if e not in [None, '']]
    shortName = drv.ShortName

    if not (drv.GetMetadataItem(gdal.DCAP_CREATE) == 'YES' or
            drv.GetMetadataItem(gdal.DCAP_CREATECOPY) == 'YES'):
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


class VRTBuilderMapTools(enum.Enum):
    IdentifySource = 'IDENTIFY_SOURCE'
    SelectExtent = 'SELECT_EXTENT'
    AlignGrid = 'ALIGN_GRID'
    CopyGrid = 'COPY_GRID'
    CopyExtent = 'COPY_EXTENT'
    CopyResolution = 'COPY_RESOLUTION'


def sourceBaseName(source) -> str:
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


def sourceIcon(source) -> QIcon:
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


class SourceRasterBandGroupNode(TreeNode):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


class SourceRasterBandNode(TreeNode):
    def __init__(self, vrtRasterInputSourceBand: VRTRasterInputSourceBand):
        assert isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand)
        super().__init__()
        self.mSrcBand = vrtRasterInputSourceBand

        b = self.mSrcBand.mBandIndex + 1
        self.setName(b)

        # self.setName('{}:{}'.format(os.path.basename(self.mSrcBand.mSource), ))
        self.setValues([self.mSrcBand.mBandName])
        self.setToolTip('band {}:{}'.format(self.mSrcBand.mBandIndex + 1, self.mSrcBand.mSource))

    def sourceBand(self) -> VRTRasterInputSourceBand:
        return self.mSrcBand

    def source(self) -> str:
        return self.mSrcBand.source()


class VRTRasterNode(TreeNode):
    def __init__(self, vrtRaster: VRTRaster):
        assert isinstance(vrtRaster, VRTRaster)
        super().__init__()
        self.mVRTRaster = vrtRaster
        self.mVRTRaster.sigBandInserted.connect(self.onBandInserted)
        self.mVRTRaster.sigBandRemoved.connect(self.onBandRemoved)

    def onBandInserted(self, index: int, vrtRasterBand):
        assert isinstance(vrtRasterBand, VRTRasterBand)
        i = vrtRasterBand.bandIndex()
        assert i == index
        node = VRTRasterBandNode(vrtRasterBand)
        self.insertChildNodes(i, node)

    def onBandRemoved(self, index: int):
        self.removeChildNodes(self.mChildren[index])


class VRTRasterBandNode(TreeNode):
    def __init__(self, virtualBand: VRTRasterBand):
        assert isinstance(virtualBand, VRTRasterBand)

        super().__init__()
        self.mVirtualBand = virtualBand
        self.setName(virtualBand.name())
        self.setIcon(QIcon(":/vrtbuilder/mIconVirtualRaster.svg"))

        virtualBand.sigNameChanged.connect(self.setName)
        virtualBand.sigSourceInserted.connect(lambda _, src: self.onSourceInserted(src))
        virtualBand.sigSourceRemoved.connect(self.onSourceRemoved)

        for src in self.mVirtualBand:
            self.onSourceInserted(src)

    def onSourceInserted(self, inputSource: VRTRasterInputSourceBand):
        assert isinstance(inputSource, VRTRasterInputSourceBand)
        assert inputSource.virtualBand() == self.mVirtualBand
        i = self.mVirtualBand.mSources.index(inputSource)

        node = VRTRasterInputSourceBandNode(self, inputSource)
        self.insertChildNodes(i, node)

    def onSourceRemoved(self, row: int, inputSource: VRTRasterInputSourceBand):
        assert isinstance(inputSource, VRTRasterInputSourceBand)

        node = self.childNodes()[row]
        if node.mSrc != inputSource:
            s = ""
        self.removeChildNodes(node)


class VRTRasterInputSourceBandNode(TreeNode):
    def __init__(self, parentNode, vrtRasterInputSourceBand):
        assert isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand)
        super(VRTRasterInputSourceBandNode, self).__init__(parentNode)
        self.setIcon(QIcon(":/vrtbuilder/mIconRaster.svg"))
        self.mSrc = vrtRasterInputSourceBand

        path = self.source()
        bn = os.path.basename(path)
        b = self.sourceBand().bandIndex() + 1

        self.setName(f'{bn}:{b}')
        self.setValues(f'{path}:{b}')
        self.setToolTip(f'Band {b} from "{path}"'
                        )

    def sourceBand(self) -> VRTRasterInputSourceBand:
        return self.mSrc

    def source(self) -> str:
        return self.mSrc.source()


class VRTRasterPreviewMapCanvas(QgsMapCanvas):
    def __init__(self, parent=None, *args, **kwds):
        super(VRTRasterPreviewMapCanvas, self).__init__(parent, *args, **kwds)
        # self.setCrsTransformEnabled(True)

        self.mVRTRaster = None
        self.mExtentRubberBand = QgsRubberBand(self, QgsWkbTypes.PolygonGeometry)
        self.mExtentRubberBand.setColor(QColor('orange'))
        self.mExtentRubberBand.setWidth(1)

        self.mSelectedSourceRubberBand = QgsRubberBand(self, QgsWkbTypes.PolygonGeometry)
        self.mSelectedSourceRubberBand.setColor(QColor('red'))
        self.mSelectedSourceRubberBand.setWidth(2)

        self.mStore = QgsMapLayerStore()

    def setExtentLineColor(self, color: QColor):
        assert isinstance(color, QColor)
        self.mExtentRubberBand.setColor(color)

    def setExtentLineWidth(self, width: int):
        self.mExtentRubberBand.setWidth(width)

    def extentLineColor(self) -> QColor:
        return self.mExtentRubberBand.color()

    def extentLineWidth(self) -> int:
        return self.mExtentRubberBand.width()

    def crs(self) -> QgsCoordinateReferenceSystem:
        return self.mapSettings().destinationCrs()

    def setVRTRaster(self, vrtRaster: VRTRaster):
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
            if isinstance(extent, QgsRectangle) and isinstance(crs,
                                                               QgsCoordinateReferenceSystem) and extent.width() > 0:
                geom = QgsGeometry.fromWkt(extent.asWktPolygon())
                self.mExtentRubberBand.addGeometry(geom, crs=crs)

    def contextMenuEvent(self, event):
        menu = QMenu()
        action = menu.addAction('Refresh')
        action.triggered.connect(self.refresh)

        action = menu.addAction('Reset')
        action.triggered.connect(self.reset)

        menu.exec_(event.globalPos())

    def setSelectedLayers(self, layers: list):

        self.mSelectedSourceRubberBand.reset()
        for layer in layers:
            assert isinstance(layer, QgsMapLayer)
            geom = QgsGeometry.fromWkt(layer.extent().asWktPolygon())
            self.mSelectedSourceRubberBand.addGeometry(geom, crs=layer.crs())

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

    def __init__(self, mapLayer: QgsRasterLayer):

        name = mapLayer.name()
        if name == '':
            name = os.path.basename(mapLayer.source())

        super().__init__(name=name)
        assert isinstance(mapLayer, QgsRasterLayer)
        assert mapLayer.dataProvider().name() == 'gdal'
        self.setIcon(QIcon(":/vrtbuilder/mIconRaster.svg"))
        self.mRasterLayer: QgsRasterLayer = mapLayer
        self.mPath: str = mapLayer.source()

        self.srcNode = TreeNode(name='Path')
        self.srcNode.setValues(mapLayer.source())

        self.crsNode = TreeNode(name='CRS')

        crs: QgsCoordinateReferenceSystem = self.mRasterLayer.crs()
        authInfo = f'{crs.description()} {crs.authid()}'
        # self.crsNode.setIcon(QIcon(':/images/themes/default/propertyicons/CRS.svg'))
        self.crsNode.setValues(authInfo)
        self.crsNode.setToolTip(crs.toWkt())
        self.bandNode = SourceRasterBandGroupNode(name='Bands')
        # self.bandNode = TreeNode(name='Bands')
        inputSourceNodes = []
        for b in range(self.mRasterLayer.bandCount()):
            bandName = self.mRasterLayer.bandName(b + 1)
            inputSource = VRTRasterInputSourceBand(self.mPath, b, bandName=bandName)
            inputSource.mBandName = bandName
            inputSource.mNoData = self.mRasterLayer.dataProvider().sourceNoDataValue(b + 1)
            inputSourceNodes.append(SourceRasterBandNode(inputSource))
        self.bandNode.appendChildNodes(inputSourceNodes)
        self.appendChildNodes([self.srcNode, self.crsNode, self.bandNode])

        s = ""
        s = ""

    def source(self) -> str:
        return self.mPath

    def sourceBands(self) -> typing.List[VRTRasterInputSourceBand]:
        return [n.mSrcBand for n in self.bandNode.mChildren if isinstance(n, SourceRasterBandNode)]

    def rasterLayer(self) -> QgsRasterLayer:
        return self.mRasterLayer


class SourceRasterFilterModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRecursiveFilteringEnabled(True)
        self.setSortRole(Qt.EditRole)
        self.setDynamicSortFilter(True)
        self.rowsInserted.connect(self.initSorting)

    def initSorting(self, idx, first, last):
        self.sort(0, Qt.AscendingOrder)
        self.rowsInserted.disconnect(self.initSorting)

    def lessThan(self, idx1: QModelIndex, idx2: QModelIndex) -> bool:

        node1 = idx1.data(Qt.UserRole)
        node2 = idx2.data(Qt.UserRole)

        if isinstance(node1, SourceRasterBandNode) and isinstance(node2, SourceRasterBandNode):
            return node1.sourceBand().bandIndex() < node2.sourceBand().bandIndex()
        if isinstance(node1, SourceRasterBandGroupNode) ^ isinstance(node2, SourceRasterBandGroupNode):
            return False
        if isinstance(node1.parentNode(), SourceRasterFileNode) and node1.parentNode() == node2.parentNode():
            return False

        return super().lessThan(idx1, idx2)

    def columnCount(self, parent=None, *args, **kwargs):

        s = ""

        idxS = self.mapToSource(parent)
        sModel = self.sourceModel()

        cntS = sModel.columnCount(idxS)

        cntF = super().columnCount(parent)

        if cntS != cntF:
            s = ""
        return super().columnCount(parent)

    def mimeTypes(self):
        return self.sourceModel().mimeTypes()

    def dropMimeData(self, mimeData, action, row, col, parentIndex):
        return self.sourceModel().dropMimeData(mimeData, action, row, col, parentIndex)

    def supportedDropActions(self):
        return self.sourceModel().supportedDropActions()

    def canDropMimeData(self, data, action, row, column, parent):
        return self.sourceModel().canDropMimeData(data, action, row, column, parent)

    def nodeNames(self, node: TreeNode) -> typing.List[str]:
        if not isinstance(node, (SourceRasterFileNode, SourceRasterBandNode)):
            return []
        else:
            return [node.name()] + [str(v) for v in node.values()]

    def filterAcceptsColumn(self, p_int, index: QModelIndex):
        return True

    def filterAcceptsRow(self, sourceRow, sourceParent):
        reg = self.filterRegExp()
        if reg.isEmpty():
            return True

        node = self.sourceModel().index(sourceRow, 0, sourceParent).data(Qt.UserRole)
        if not isinstance(node, TreeNode):
            return False

        # if isinstance(node.parentNode(), SourceRasterFileNode) and node == node.parentNode().bandNode:
        #   return True

        if not isinstance(node, (SourceRasterFileNode, SourceRasterBandNode)):
            return False
        for name in self.nodeNames(node):
            if reg.indexIn(name) >= 0:
                return True
        """
        if isinstance(node, SourceRasterFileNode):
            for bandNode in node.bandNode.childNodes():
                for name in self.nodeNames(bandNode):
                    if reg.indexIn(name) >= 0:
                        return True
        """
        return False


class SourceRasterModel(TreeModel):
    sigSourcesAdded = pyqtSignal()
    sigSourcesRemoved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnNames(['File/Band', 'Value/Description'])

    def __len__(self):
        return len(self.rasterSources())

    def __iter__(self):
        return iter(self.rasterSources())

    def __contains__(self, file):
        return pathlib.Path(file).resolve().as_posix() in self.rasterSources()

    def rasterSources(self) -> typing.List[str]:
        return [pathlib.Path(l.source()).as_posix() for l in self.rasterLayers()]

    def rasterLayers(self) -> list:
        """
        Returns the list of QgsRasterLayers behind all input sources.
        :return: [list-of-QgsRasterLayers]
        """
        return [n.rasterLayer() for n in self.rootNode() if isinstance(n, SourceRasterFileNode)]

    def addSource(self, rasterSource):
        self.addSources([rasterSource])

    def addSources(self, rasterSources):
        assert isinstance(rasterSources, list)
        existingSources = self.rasterSources()

        newLayers = qgsRasterLayers(rasterSources)

        newLayers = [l for l in newLayers if isinstance(l, QgsRasterLayer) and
                     pathlib.Path(l.source()).as_posix() not in existingSources]

        if len(newLayers) > 0:
            newNodes = [SourceRasterFileNode(lyr) for lyr in newLayers]
            self.rootNode().appendChildNodes(newNodes)
            self.sigSourcesAdded.emit()

    def file2node(self, file: str) -> SourceRasterFileNode:
        for node in self.mRootNode.childNodes():
            if isinstance(node, SourceRasterFileNode) and node.mPath == file:
                return node
        return None

    def file2layer(self, file: str) -> QgsRasterLayer:
        node = self.file2node(file)
        if isinstance(node, SourceRasterFileNode):
            return node.rasterLayer()
        else:
            return None

    def removeFiles(self, listOfFiles):
        assert isinstance(listOfFiles, list)

        toRemove = [n for n in self.rootNode().childNodes() \
                    if isinstance(n, SourceRasterFileNode) and n.source() in listOfFiles]

        if len(toRemove) > 0:
            self.rootNode().removeChildNodes(toRemove)
            self.sigSourcesRemoved.emit()

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsDropEnabled

        flags = super().flags(index)
        node = index.data(Qt.UserRole)
        # return flags
        flags |= Qt.ItemIsSelectable
        if isinstance(node, (SourceRasterFileNode, SourceRasterBandNode)):
            flags |= Qt.ItemIsDragEnabled
        else:
            s = ""
        return flags

    def dropMimeData(self, mimeData, action, row, col, parentIndex):

        assert isinstance(mimeData, QMimeData)

        if mimeData.hasUrls():
            self.addSources(mimeData.urls())
            return True

        elif 'application/qgis.layertreemodeldata' in mimeData.formats():
            doc = QDomDocument()
            doc.setContent(mimeData.data('application/qgis.layertreemodeldata'))
            # types.append('application/qgis.layertreemodeldata')
            # types.append('application/x-vnd.qgis.qgis.uri')
            # print(doc.toString())
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

    def mimeTypes(self):
        # specifies the mime types handled by this model
        types = []
        types.append('text/uri-list')
        types.append('application/qgis.layertreemodeldata')
        types.append('application/x-vnd.qgis.qgis.uri')
        return types

    def mimeData(self, indexes) -> QMimeData:
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


class SourceRasterTreeView(TreeView):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def dragEnterEvent(self, event):
        assert isinstance(event, QDragEnterEvent)
        supported = self.model().mimeTypes()
        for f in event.mimeData().formats():
            if f in supported:
                event.acceptProposedAction()
                break


class VRTRasterTreeView(TreeView):
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        idx = self.indexAt(event.pos())
        if not idx.isValid():
            pass
        vrtModel: VRTRasterTreeModel = self.model()

        currentIndex = self.selectionModel().currentIndex()
        selectedRows = self.selectionModel().selectedRows()
        selectedNodes = [idx.data(role=Qt.UserRole) for idx in selectedRows]

        selectedSourceNodes = [n for n in selectedNodes if isinstance(n, VRTRasterInputSourceBandNode)]
        selectedVRTBandNodes = [n for n in selectedNodes if isinstance(n, VRTRasterBandNode)]

        menu = QMenu(parent=self)

        if len(selectedSourceNodes) > 0:
            a = menu.addAction('Remove source band(s)')
            a.setToolTip(f'Remove {len(selectedSourceNodes)} selected source band(s)')
            a.triggered.connect(lambda *args, nodes=selectedSourceNodes: vrtModel.removeNodes(nodes))

        if isinstance(currentIndex, QModelIndex) and isinstance(currentIndex.data(role=Qt.UserRole), VRTRasterBandNode):
            a = menu.addAction('Rename')
            a.setToolTip('Change the virtual band name.')
            a.triggered.connect(lambda *args, idx=currentIndex: self.edit(idx))

        if len(selectedVRTBandNodes) > 0:
            a = menu.addAction('Remove virtual band(s)')
            a.setToolTip(f'Remove {len(selectedVRTBandNodes)} selected virtual band(s)')
            a.triggered.connect(lambda *args, nodes=selectedVRTBandNodes: vrtModel.removeNodes(nodes))

        menu.exec_(self.viewport().mapToGlobal(event.pos()))


class VRTSelectionModel(QItemSelectionModel):
    def __init__(self, vrtRasterModel, sourceRasterModel: SourceRasterModel, mapCanvas: VRTRasterPreviewMapCanvas,
                 parent=None):
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

    def selectedSourceBandNodes(self) -> list:
        indexes = self.selectedIndexes()
        selectedFileNodes = self.mVRTRasterModel.indexes2nodes(indexes)
        return [n for n in selectedFileNodes if isinstance(n, VRTRasterInputSourceBandNode)]

    def selectedSourceLayers(self) -> list:
        return [self.mSourceRasterModel.file2layer(f) for f in self.selectedSourceFiles()]

    def selectedSourceFiles(self) -> list:
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


class DropMode(enum.Enum):
    NestedStack = 'NESTET_STACK'
    Stack = 'PURE_STACK'

    @staticmethod
    def toolTip(mode) -> str:
        if mode == DropMode.NestedStack:
            return 'Drop source bands with same band numbers into same virtual bands (nested by band number).'
        elif mode == DropMode.Stack:
            return 'Drop source bands with same band numbers into different virtual bands (stacked bands).'
        else:
            raise NotImplementedError()

    @staticmethod
    def icon(mode) -> QIcon:
        if mode == DropMode.NestedStack:
            return QIcon(':/vrtbuilder/mOptionMosaikFiles.svg')
        elif mode == DropMode.Stack:
            return QIcon(':/vrtbuilder/mOptionStackFiles.svg')
        else:
            raise NotImplementedError()


class VRTRasterTreeModel(TreeModel):

    def __init__(self, vrtRaster: VRTRaster, parent=None):
        assert isinstance(vrtRaster, VRTRaster)
        rootNode = VRTRasterNode(vrtRaster)
        super().__init__(parent, rootNode=rootNode)
        self.mVRTRaster = vrtRaster
        self.setColumnNames(['Virtual/Source Band', 'Source Path'])
        self.mDropMode: DropMode = DropMode.NestedStack

    def setDropMode(self, mode: DropMode):
        assert isinstance(mode, DropMode)
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

    def srcFileIndices(self, srcFile) -> list:
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

        if self.mDropMode == DropMode.NestedStack:

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
        elif self.mDropMode == DropMode.Stack:
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

    def __init__(self, canvas, layerType: QgsMapToolIdentify.Type):
        super(MapToolIdentifySource, self).__init__(canvas)
        self.mCanvas = canvas
        assert isinstance(layerType, QgsMapToolIdentify.Type)
        self.mLayerType: QgsMapToolIdentify.Type = layerType
        self.setCursor(Qt.CrossCursor)

    def canvasPressEvent(self, e):

        pos = self.toMapCoordinates(e.pos())
        # results = self.identify(QgsGeometry.fromWkt(pos.asWkt()), QgsMapToolIdentify.TopDownAll, self.mLayerType)
        results = self.identify(e.x(), e.y(), QgsMapToolIdentify.TopDownAll, self.mLayerType)
        layers = [r.mLayer for r in results if isinstance(r.mLayer, QgsMapLayer)]
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


class AboutWidget(QDialog):
    def __init__(self, parent=None):
        super(AboutWidget, self).__init__(parent)
        # self.setupUi(self)
        loadUi(DIR_UI / 'about.ui', self)
        self.labelVersion.setText('Version {}'.format(__version__))


class VRTBuilderWidget(QMainWindow):
    sigRasterCreated = pyqtSignal([str], [str, bool])
    sigAboutCreateCurrentMapTools = pyqtSignal()

    def __init__(self, parent=None):
        super(VRTBuilderWidget, self).__init__(parent)

        loadUi(DIR_UI / 'vrtbuilder.ui', self)
        # self.webView.setUrl(QUrl('help.html'))
        title = self.windowTitle()
        self.setWindowIcon(QIcon(':/vrtbuilder/mActionNewVirtualLayer.svg'))
        if __version__ not in title:
            title = '{} {}'.format(title, __version__)
            self.setWindowTitle(title)

        self.menuView: QMenu
        self.menuView.addAction(self.toolBar.toggleViewAction())
        self.menuView.addSeparator()
        for dockWidget in self.findChildren(QDockWidget):
            self.menuView.addAction(dockWidget.toggleViewAction())

        self.sBar = QgsStatusBar()
        self.sBar.setParentStatusBar(self.statusBar())
        self.statusBar().addPermanentWidget(self.sBar, 1)
        self.statusBar().setStyleSheet("QStatusBar::item {border: none;}")

        btnSave: QPushButton = self.buttonBox.button(QDialogButtonBox.Save)
        self.actionSaveVRT.changed.connect(lambda: btnSave.setEnabled(self.actionSaveVRT.isEnabled()))
        btnSave.setIcon(self.actionSaveVRT.icon())
        btnSave.setText(self.actionSaveVRT.text())
        btnSave.setToolTip(self.actionSaveVRT.toolTip())
        btnSave.clicked.connect(self.actionSaveVRT.trigger)

        self.buttonBox.button(QDialogButtonBox.Close).clicked.connect(self.close)

        self.progressBar = QProgressBar()
        self.sBar.addPermanentWidget(self.progressBar, QgsStatusBar.AnchorLeft)
        self.sBar.addPermanentWidget(self.buttonBox)
        self.previewMap: QgsMapCanvas
        assert isinstance(self.previewMap, QgsMapCanvas)

        self.mSourceFileModel = SourceRasterModel(parent=self.treeViewSourceFiles)
        self.mSourceFileModel.sigSourcesRemoved.connect(self.buildButtonMenus)
        self.mSourceFileModel.sigSourcesAdded.connect(self.buildButtonMenus)
        self.mSourceFileModel.rowsInserted.connect(self.onRowsInsertedTEST)
        self.mSourceFileProxyModel = SourceRasterFilterModel()
        self.mSourceFileProxyModel.setSourceModel(self.mSourceFileModel)
        self.mSourceFileProxyModel.sort(0, Qt.DescendingOrder)
        self.tbSourceFileFilter.textChanged.connect(self.onSourceFileFilterChanged)
        self.cbSourceFileFilterRegex.clicked.connect(
            lambda: self.onSourceFileFilterChanged(self.tbSourceFileFilter.text()))

        assert isinstance(self.treeViewSourceFiles, SourceRasterTreeView)
        self.treeViewSourceFiles.setModel(self.mSourceFileProxyModel)
        self.treeViewSourceFiles.setDragEnabled(True)
        self.treeViewSourceFiles.setAcceptDrops(True)
        self.treeViewSourceFiles.setDropIndicatorShown(True)
        self.treeViewSourceFiles.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.treeViewSourceFiles.setSortingEnabled(True)

        self.cbInMemoryOutput.clicked.connect(self.onInMemoryOutputTriggered)

        selectionModel = self.treeViewSourceFiles.selectionModel()
        self.actionRemoveSourceFiles.setEnabled(False)
        selectionModel.selectionChanged.connect(self.onSrcModelSelectionChanged)
        self.onSrcModelSelectionChanged(QItemSelection(), QItemSelection())
        self.tbNoData.setValidator(QDoubleValidator())

        filter = 'GDAL Virtual Raster (*.vrt);;GeoTIFF (*.tiff *.tif);;ENVI (*.bsq *.bil *.bip)'

        self.mQgsFileWidget.setFilter(filter)
        self.mQgsFileWidget.setStorageMode(QgsFileWidget.SaveFile)
        self.mQgsFileWidget.fileChanged.connect(self.validateInputs)

        self.mVRTRaster = VRTRaster(self)

        # self.vrtRaster.sigSourceBandInserted.connect(self.resetMap)
        # self.vrtRaster.sigSourceRasterAdded.connect(self.resetMap)

        assert isinstance(self.previewMap, VRTRasterPreviewMapCanvas)

        self.mVRTRaster.sigCrsChanged.connect(self.updateSummary)
        # self.mVRTRaster.sigSourceBandInserted.connect(self.onVRTSourceBandAdded)

        self.mVRTRaster.sigSourceBandInserted.connect(self.onSourceFilesChanged)
        self.mVRTRaster.sigSourceBandRemoved.connect(self.onSourceFilesChanged)
        self.mVRTRaster.sigBandInserted.connect(self.updateSummary)
        self.mVRTRaster.sigBandRemoved.connect(self.updateSummary)
        self.mVRTRaster.sigBandRemoved.connect(self.validateInputs)
        self.mVRTRaster.sigExtentChanged.connect(self.updateSummary)
        self.mVRTRaster.sigResolutionChanged.connect(self.updateSummary)
        self.previewMap.setVRTRaster(self.mVRTRaster)
        assert isinstance(self.treeViewVRT, VRTRasterTreeView)
        self.treeViewVRT: VRTRasterTreeView
        self.mVRTRasterTreeModel = VRTRasterTreeModel(self.mVRTRaster, parent=self.treeViewVRT)

        self.treeViewVRT.setModel(self.mVRTRasterTreeModel)

        self.vrtTreeSelectionModel = VRTSelectionModel(self.treeViewVRT.model(), self.mSourceFileModel, self.previewMap)
        self.vrtTreeSelectionModel.selectionChanged.connect(self.onVRTSelectionChanged)

        self.treeViewVRT.setSelectionModel(self.vrtTreeSelectionModel)

        # 2. expand the parent nodes
        self.treeViewVRT.setAutoExpandDelay(50)
        self.treeViewVRT.setDragEnabled(True)

        self.initActions()

        self.mMapToolInstances: typing.List[QgsMapTool] = []
        self.mCurrentMapToolKey: VRTBuilderMapTools = None
        self.mCurrentMapToolArgs: list = []
        self.mCurrentMapToolKwds: dict = {}

        self.restoreLastSettings()
        self.validateInputs()
        self.resetMap()

        self.sigAboutCreateCurrentMapTools.connect(lambda *args, c=self.previewMap:
                                                   self.createCurrentMapTool(c))

    def onRowsInsertedTEST(self, parent: QModelIndex, first: int, last: int):
        topLeft = self.mSourceFileModel.index(first, 0, parent)
        bottomRight = self.mSourceFileModel.index(last, self.mSourceFileModel.columnCount(parent) - 1, parent)
        self.mSourceFileModel.dataChanged.emit(topLeft, bottomRight)

    def initActions(self):

        self.btnCopyResolution.setDefaultAction(self.actionCopyResolution)
        self.btnCopyExtent.setDefaultAction(self.actionCopyExtent)
        self.bntCopyGrid.setDefaultAction(self.actionCopyGrid)
        self.btnAlignGrid.setDefaultAction(self.actionAlignGrid)
        self.bntDrawExtent.setDefaultAction(self.actionSelectSpatialExtent)

        self.actionSaveVRT.triggered.connect(self.saveFile)

        self.actionCopyResolution.triggered.connect(lambda: self.setCurrentMapTool(VRTBuilderMapTools.CopyResolution))
        self.actionCopyExtent.triggered.connect(lambda: self.setCurrentMapTool(VRTBuilderMapTools.CopyExtent))
        self.actionCopyGrid.triggered.connect(lambda: self.setCurrentMapTool(VRTBuilderMapTools.CopyGrid))
        self.actionAlignGrid.triggered.connect(lambda: self.setCurrentMapTool(VRTBuilderMapTools.AlignGrid))
        self.actionSelectSpatialExtent.triggered.connect(
            lambda: self.setCurrentMapTool(VRTBuilderMapTools.SelectExtent))
        self.buildButtonMenus()  # adds QMenus to each button

        self.optionStackMode: QAction
        self.optionStackMode.toggled.connect(self.onStackModelToggled)
        self.optionStackMode.setChecked(False)

        self.onInMemoryOutputTriggered(False)
        reg = QRegExp(r"^\D[^ ]*\.vrt$")
        self.lineEditInMemory.setValidator(QRegExpValidator(reg))
        self.lineEditInMemory.textChanged.connect(self.validateInputs)
        #
        for tb in [self.tbBoundsXMin, self.tbBoundsXMax, self.tbBoundsYMin, self.tbBoundsYMax]:
            # .textEdited is emitted on "manual" changed only
            tb.textEdited.connect(lambda: self.calculateGrid(changedExtent=True))
            tb.setValidator(QDoubleValidator(-999999999999999999999.0, 999999999999999999999.0, 20))

        self.sbResolutionX.valueChanged[float].connect(
            lambda r, w=self.sbResolutionX: self.onResolutionValueChanged(w, r))
        self.sbResolutionY.valueChanged[float].connect(
            lambda r, w=self.sbResolutionX: self.onResolutionValueChanged(w, r))

        self.sbRasterWidth.valueChanged.connect(lambda: self.calculateGrid(changedSize=True))
        self.sbRasterHeight.valueChanged.connect(lambda: self.calculateGrid(changedSize=True))

        self.cbResampling.clear()
        self.cbResampling.setModel(RESAMPLE_ALGS)

        # self.btnAddFromRegistry.setDefaultAction(self.actionAddFromRegistry)
        self.actionAddFromRegistry.triggered.connect(self.loadSrcFromMapLayerRegistry)
        # self.btnAddSrcFiles.setDefaultAction(self.actionAddSourceFiles)

        self.actionAddSourceFiles.triggered.connect(self.onAddSourceFiles)
        # self.btnRemoveSrcFiles.setDefaultAction(self.actionRemoveSourceFiles)

        self.actionRemoveSourceFiles.triggered.connect(self.onRemoveSelectedSourceFiles)

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

        # self.btnAddVirtualBand.setDefaultAction(self.actionAddVirtualBand)
        self.actionAddVirtualBand.triggered.connect(
            lambda: self.mVRTRaster.addVirtualBand(VRTRasterBand(name='Band {}'.format(len(self.mVRTRaster) + 1))))

        # self.btnRemoveVirtualBands.setDefaultAction(self.actionRemoveVirtualBands)
        self.actionRemoveVirtualBands.triggered.connect(lambda: self.mVRTRasterTreeModel.removeNodes(
            self.mVRTRasterTreeModel.indexes2nodes(self.treeViewVRT.selectedIndexes())
        ))

        # self.btnLoadVRT.setDefaultAction(self.actionLoadVRT)

        self.actionAbout.triggered.connect(lambda: AboutWidget(self).exec_())
        self.actionDocumentation.triggered.connect(lambda: webbrowser.open(URL_HOMEPAGE))
        self.actionIssueTracker.triggered.connect(lambda: webbrowser.open(URL_ISSUETRACKER))

        self.crsSelectionWidget.setMessage('Set VRT CRS')
        self.crsSelectionWidget.crsChanged.connect(self.mVRTRaster.setCrs)

        # map tools

        self.actionPan.triggered.connect(lambda: self.setCurrentMapTool(MapTools.Pan))
        self.actionZoomIn.triggered.connect(lambda: self.setCurrentMapTool(MapTools.ZoomIn))
        self.actionZoomOut.triggered.connect(lambda: self.setCurrentMapTool(MapTools.ZoomOut))
        self.actionSelectSourceLayer.triggered.connect(
            lambda: self.setCurrentMapTool(VRTBuilderMapTools.IdentifySource))

        self.btnZoomIn.setDefaultAction(self.actionZoomIn)
        self.btnZoomOut.setDefaultAction(self.actionZoomOut)
        self.btnPan.setDefaultAction(self.actionPan)
        self.btnZoomExtent.clicked.connect(self.previewMap.reset)

        self.btnSelectFeature.setDefaultAction(self.actionSelectSourceLayer)

        self.actionLoadVRT.triggered.connect(self.onLoadVRT)

        # extents
        self.cbBoundsFromSourceFiles.clicked.connect(self.onUseAutomaticExtent)
        self.cbBoundsFromSourceFiles.setChecked(True)
        self.onUseAutomaticExtent(True)

    def onResolutionValueChanged(self, sender: QWidget, value: float):
        if sender == self.sbResolutionX:
            if self.cbLinkResolutionXY.isChecked():
                self.sbResolutionY.setValue(value)
                return
        if sender == self.sbResolutionY:
            pass

        self.calculateGrid(changedResolution=True)

    def onStackModelToggled(self, is_nested: bool):

        if is_nested == True:
            dropMode = DropMode.NestedStack
        else:
            dropMode = DropMode.Stack

        self.optionStackMode.setIcon(DropMode.icon(dropMode))
        self.optionStackMode.setToolTip(DropMode.toolTip(dropMode))
        self.mVRTRasterTreeModel.setDropMode(dropMode)

    def onLoadVRT(self, *args):
        fn, filer = QFileDialog.getOpenFileName(self, "Open VRT file", filter='GDAL Virtual Raster (*.vrt)',
                                                directory='')

        if len(fn) > 0:
            self.loadVRT(fn)

    def onAddSourceFiles(self, *args):

        files, filer = QFileDialog.getOpenFileNames(self, "Open raster images", directory='')
        if len(files) > 0:
            self.addSourceFiles(files)

    def onRemoveSelectedSourceFiles(self, *args):
        sm = self.treeViewSourceFiles.selectionModel()
        m = self.treeViewSourceFiles.model()

        to_remove = set()
        rows = sm.selectedRows()
        for rowIdx in rows:
            node = m.data(rowIdx, Qt.UserRole)
            if isinstance(node, SourceRasterFileNode):
                to_remove.add(node.source())
            elif isinstance(node, SourceRasterBandNode):
                to_remove.add(node.source())
            else:
                s = ""
        to_remove = list(to_remove)
        if len(to_remove) > 0:
            self.mSourceFileModel.removeFiles(to_remove)

        # self.sourceFileModel.removeFiles(    [n.mPath for n in self.selectedSourceFileNodes()]

    def onInMemoryOutputTriggered(self, b):
        if b:
            self.mQgsFileWidget.setVisible(False)
            self.frameInMemoryPath.setVisible(True)

        else:
            self.mQgsFileWidget.setVisible(True)
            self.frameInMemoryPath.setVisible(False)

        self.validateInputs()

    def loadVRT(self, path):
        if path is not None and os.path.isfile(path):
            self.mVRTRaster.loadVRT(path)

    def setCurrentMapTool(self, mapTool: typing.Union[VRTBuilderMapTools, MapTools], mapToolArgs=[], mapToolKwds={}):
        """
        Sets the current map tool and calls sigAboutCreateCurrentMapTools, which other applications
        can use to register on
        :param mapTool:
        :param mapToolArgs:
        :param mapToolKwds:
        :return:
        """
        assert isinstance(mapTool, (VRTBuilderMapTools, MapTools))
        self.mCurrentMapToolKey = mapTool
        self.mCurrentMapToolArgs = mapToolArgs
        self.mCurrentMapToolKwds = mapToolKwds
        self.mMapToolInstances.clear()
        # receivers can add mapcanvases by calling createCurrentMapTool(mapCanvas)
        self.sigAboutCreateCurrentMapTools.emit()

    def createCurrentMapTool(self, canvas: QgsMapCanvas):
        assert isinstance(canvas, QgsMapCanvas)
        if not isinstance(self.mCurrentMapToolKey, (VRTBuilderMapTools, MapTools)):
            return

        mapTool: QgsMapTool = None

        if self.mCurrentMapToolKey == VRTBuilderMapTools.IdentifySource:
            def onLayersSelected(layers: list):
                sources = [l.source() for l in layers]
                self.vrtTreeSelectionModel.setSelectedSourceFiles(sources)

            mapTool = MapToolIdentifySource(canvas, QgsMapToolIdentify.RasterLayer)
            mapTool.sigMapLayersIdentified.connect(onLayersSelected)
            mapTool.sigEmptySelection.connect(lambda: onLayersSelected([]))

        elif self.mCurrentMapToolKey == VRTBuilderMapTools.SelectExtent:
            mapTool = SpatialExtentMapTool(canvas)
            mapTool.sigSpatialExtentSelected[QgsCoordinateReferenceSystem, QgsRectangle].connect(
                self.onSetSpatialExtent)

        elif self.mCurrentMapToolKey == VRTBuilderMapTools.CopyResolution:
            mapTool = MapToolIdentifySource(canvas, QgsMapToolIdentify.RasterLayer)

            def onLayerSelected(lyr):
                assert isinstance(lyr, QgsRasterLayer)
                res = QSizeF(lyr.rasterUnitsPerPixelX(), lyr.rasterUnitsPerPixelY())

                self.mVRTRaster.setResolution(res, crs=lyr.crs())

            mapTool.sigMapLayerIdentified.connect(onLayerSelected)

        elif self.mCurrentMapToolKey == VRTBuilderMapTools.CopyExtent:
            mapTool = MapToolIdentifySource(canvas, QgsMapToolIdentify.AllLayers)
            mapTool.sigMapLayerIdentified.connect(
                lambda lyr: self.mVRTRaster.setExtent(lyr.extent(), crs=lyr.crs()))

        elif self.mCurrentMapToolKey == VRTBuilderMapTools.CopyGrid:
            mapTool = MapToolIdentifySource(canvas, QgsMapToolIdentify.RasterLayer)
            mapTool.sigMapLayerIdentified.connect(lambda lyr: self.mVRTRaster.alignToRasterGrid(lyr, True))

        elif self.mCurrentMapToolKey == VRTBuilderMapTools.AlignGrid:
            mapTool = MapToolIdentifySource(canvas, QgsMapToolIdentify.RasterLayer)
            mapTool.sigMapLayerIdentified.connect(lambda lyr: self.mVRTRaster.alignToRasterGrid(lyr, False))
        elif isinstance(self.mCurrentMapToolKey, MapTools):
            mapTool = MapTools.create(self.mCurrentMapToolKey, canvas,
                                      *self.mCurrentMapToolArgs, **self.mCurrentMapToolKwds)
        else:

            raise NotImplementedError('Maptool key unhandled "{}"'.format(self.mCurrentMapToolKey))

        if isinstance(mapTool, QgsMapTool):
            canvas.setMapTool(mapTool)
            self.mMapToolInstances.append(mapTool)

    @pyqtSlot(QgsCoordinateReferenceSystem, QgsRectangle)
    def onSetSpatialExtent(self, crs: QgsCoordinateReferenceSystem, rect: QgsRectangle):
        self.setExtent(SpatialExtent(crs, rect))

    def onSourceFileFilterChanged(self, text):

        useRegex = self.cbSourceFileFilterRegex.isChecked()
        if useRegex:
            self.mSourceFileProxyModel.setFilterRegExp(text)
        else:
            self.mSourceFileProxyModel.setFilterWildcard(text)
        pass

    @pyqtSlot(SpatialExtent)
    def setExtent(self, spatialExtent: SpatialExtent):
        """
        Sets the boundaries of destination raster image
        :param bbox: QgsRectangle
        :param crs: Target QgsCoordinateReferenceSystem. Defaults to the VRT crs.
        """
        assert isinstance(spatialExtent, SpatialExtent)

        assert isinstance(spatialExtent, SpatialExtent), 'Got {} instead SpatialExtent'.format(str(spatialExtent))
        if not isinstance(self.mVRTRaster.crs(), QgsCoordinateReferenceSystem):
            self.mVRTRaster.setCrs(spatialExtent.crs())
        spatialExtent = spatialExtent.toCrs(self.mVRTRaster.crs())
        self.mVRTRaster.setExtent(spatialExtent)

        self.validateInputs()

    def setBoundsFromSource(self, source):
        """Copies the spatial extent from a given raster or vector source"""
        lyr = qgsMapLayer(source)
        if isinstance(lyr, QgsMapLayer):
            spatialExtent = SpatialExtent.fromLayer(lyr)
            if isinstance(spatialExtent, SpatialExtent):
                self.setExtent(spatialExtent)

    def setResolutionFromSource(self, source):
        """Copies the pixel resolution from a QgsRasterLayer"""
        lyr = qgsRasterLayer(source)
        if isinstance(lyr, QgsRasterLayer):
            self.mVRTRaster.setResolution(resolution(lyr), crs=lyr.crs())

    def setGridFrom(self, source):
        """
        Copies the raster grid (CRS, extent, pixel size) from a raster source
        :param source: any type
        """
        lyr = qgsRasterLayer(source)
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

    def onSourceFilesChanged(self, *args):

        if self.cbBoundsFromSourceFiles.isChecked():
            self.calculateGrid(changedExtent=True)
        self.updateSummary()

    def onUseAutomaticExtent(self, auto: bool):

        for a in [self.actionSelectSpatialExtent, self.actionCopyExtent, self.actionCopyGrid]:
            a.setDisabled(auto)

        for w in [self.tbBoundsXMin, self.tbBoundsXMax, self.tbBoundsYMin, self.tbBoundsYMax, self.sbRasterWidth,
                  self.sbRasterHeight]:
            w.setDisabled(auto)

    def calculateGrid(self, changedResolution: bool = False, changedExtent: bool = False, changedCrs: bool = False,
                      changedSize: bool = False):

        n = sum([changedResolution, changedExtent, changedCrs, changedSize])
        assert n <= 1, 'only one aspect can be changed in the same call of "calculateGrid"'

        if changedResolution:
            # recalculate the grid with new pixel resolution
            res = QSizeF(self.sbResolutionX.value(), self.sbResolutionY.value())
            if res.width() > 0 and res.height() > 0:
                self.mVRTRaster.setResolution(res)
            return

        if changedSize:
            # recalculate grid with new raster size
            width = max(self.sbRasterWidth.value(), 1)
            height = max(self.sbRasterHeight.value(), 1)
            self.mVRTRaster.setSize(QSize(width, height))
            pass

        if changedCrs:
            pass

        if changedExtent:
            # recalculate with new extent

            if self.cbBoundsFromSourceFiles.isChecked():
                # derive from source files
                extent = self.mVRTRaster.fullSourceRasterExtent()
                if isinstance(extent, QgsRectangle):
                    self.mVRTRaster.setExtent(extent)

            else:
                values = [tb.text() for tb in
                          [self.tbBoundsXMin, self.tbBoundsYMin, self.tbBoundsXMax, self.tbBoundsYMax]]
                if '' not in values:
                    S = ""
                    values = [float(v) for v in values]
                    rectangle = QgsRectangle(*values)
                    if rectangle.width() > 0 and rectangle.height() > 0:
                        self.mVRTRaster.setExtent(rectangle)

        self.validateInputs()

    def validateInputs(self, *args):

        isValid = len(self.mVRTRaster.sourceRaster()) > 0
        if not self.cbBoundsFromSourceFiles.isEnabled():
            for tb in [self.tbBoundsXMin, self.tbBoundsXMax, self.tbBoundsYMin, self.tbBoundsYMax]:
                state, _, _ = tb.validator().validate(tb.text(), 0)
                isValid &= state == QValidator.Acceptable
            if isValid:
                isValid &= float(self.tbBoundsXMin.text()) < float(self.tbBoundsXMax.text())
                isValid &= float(self.tbBoundsYMin.text()) < float(self.tbBoundsYMax.text())

        assert isinstance(self.buttonBox, QDialogButtonBox)

        path = self.outputPath()
        if len(path) > 0:
            ext = os.path.splitext(path)[-1].lower()
            isValid &= ext in ['.vrt', '.bsq', '.tif', '.tiff']
        else:
            isValid = False

        self.actionSaveVRT.setEnabled(isValid)

    def restoreDefaultSettings(self):
        self.cbAddToMap.setChecked(True)
        self.cbCRSFromInputData.setChecked(True)
        from os.path import expanduser
        self.tbOutputPath.setText(os.path.join(expanduser('~'), 'output.vrt'))
        self.cbBoundsFromSourceFiles.setChecked(True)
        self.saveSettings()

    def saveSettings(self):
        _settings = settings()
        assert isinstance(_settings, QSettings)
        _settings.setValue('PATH_SAVE', self.mQgsFileWidget.filePath())

        _settings.setValue('AUTOMATIC_BOUNDS', self.cbBoundsFromSourceFiles.isChecked())

    def restoreLastSettings(self):

        _settings = settings()
        assert isinstance(_settings, QSettings)
        from os.path import expanduser
        self.mQgsFileWidget.setFilePath(_settings.value('PATH_SAVE', os.path.join(expanduser('~'), 'output.vrt')))
        self.cbBoundsFromSourceFiles.setChecked(bool(_settings.value('AUTOMATIC_BOUNDS', True)))

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
        self.actionRemoveVirtualBands.setEnabled(selected.count() > 0)
        # 2. expand the parent nodes
        model = self.mVRTRasterTreeModel
        nodes = [model.idx2node(idx) for idx in selected.indexes()]
        selected = set([model.node2idx(n.parent()) for n in nodes if isinstance(n, VRTRasterInputSourceBandNode)])
        for idx in selected:
            self.treeViewVRT.expand(idx)

    def loadSrcFromMapLayerRegistry(self, *args):
        # reg = QgsMapLayerRegistry.instance()

        sources = set(
            lyr.source() for lyr in list(QgsProject.instance().mapLayers().values()) if isinstance(lyr, QgsRasterLayer))
        sources = list(sources)
        sources = sorted(sources, key=lambda s: os.path.basename(s))

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

    def outputPath(self) -> str:

        inMemory = self.cbInMemoryOutput.isChecked()
        if inMemory:
            path = '/vsimem/' + self.lineEditInMemory.text()
        else:
            path = self.mQgsFileWidget.filePath()
        return pathlib.Path(path).resolve().as_posix()

    def saveFile(self):

        if len(self.mVRTRaster) == 0:
            return

        dsDst = None
        path = self.outputPath()
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

            self.sBar.showMessage('Save {}...'.format(path), 2000)
            dsDst = gdal.Translate(path, pathVrt, options=options)
            self.fullProgress()

        else:
            pathVrt = path
            self.sBar.clearMessage()
            dsDst = self.mVRTRaster.saveVRT(pathVrt)
            self.sBar.showMessage('{} saved'.format(pathVrt), 2000)
            self.fullProgress()
        if isinstance(dsDst, gdal.Dataset):
            self.sBar.showMessage('{} saved'.format(path), 2000)
        else:
            self.sBar.showMessage('Failed to save {}!'.format(path), 2000)

        openRaster: bool = self.openCreatedRaster()

        self.sigRasterCreated[str].emit(path)
        self.sigRasterCreated[str, bool].emit(path, openRaster)

        self.saveSettings()

    def openCreatedRaster(self) -> bool:
        return self.cbAddToMap.isChecked()

    def fullProgress(self):
        self.progressBar.setValue(100)
        QTimer.singleShot(2000, lambda: self.progressBar.setValue(0))

    def onSrcModelSelectionChanged(self, selected, deselected):

        self.actionRemoveSourceFiles.setEnabled(selected.count() > 0)
        selectedSources = set()
        for idx in selected.indexes():
            assert isinstance(idx, QModelIndex)
            node = idx.data(Qt.UserRole)
            if isinstance(node, (SourceRasterBandNode, SourceRasterFileNode)):
                selectedSources.add(node.source())
            if len(selectedSources) > 1:
                break
        self.optionStackMode.setEnabled(len(selectedSources) > 1)

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

    def mapReset(self):

        self.previewMap.refresh()
