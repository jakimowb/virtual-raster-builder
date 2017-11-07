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
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
import os, pickle

from collections import OrderedDict

from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from osgeo import gdal, osr

from vrtbuilder.virtualrasters import VRTRaster, VRTRasterBand, VRTRasterInputSourceBand, RasterBounds
from vrtbuilder.utils import loadUi

class TreeNode(QObject):
    sigWillAddChildren = pyqtSignal(QObject, int, int)
    sigAddedChildren = pyqtSignal(QObject, int, int)
    sigWillRemoveChildren = pyqtSignal(QObject, int, int)
    sigRemovedChildren = pyqtSignal(QObject, int, int)
    sigUpdated = pyqtSignal(QObject)

    def __init__(self, parentNode, name=None):
        super(TreeNode, self).__init__()
        self.mParent = parentNode

        self.mChildren = []
        self.mName = name
        self.mValues = []
        self.mIcon = None
        self.mToolTip = None


        if isinstance(parentNode, TreeNode):
            parentNode.appendChildNodes(self)

    def nodeIndex(self):
        return self.mParent.mChildren.index(self)

    def next(self):
        i = self.nodeIndex()
        if i < len(self.mChildren.mChildren):
            return self.mParent.mChildren[i+1]
        else:
            return None

    def previous(self):
        i = self.nodeIndex()
        if i > 0:
            return self.mParent.mChildren[i - 1]
        else:
            return None

    def detach(self):
        """
        Detaches this TreeNode from its parent TreeNode
        :return:
        """
        if isinstance(self.mParent, TreeNode):
            self.mParent.mChildren.remove(self)
            self.setParentNode(None)

    def appendChildNodes(self, listOfChildNodes):
        self.insertChildNodes(len(self.mChildren), listOfChildNodes)

    def insertChildNodes(self, index, listOfChildNodes):
        assert index <= len(self.mChildren)
        if isinstance(listOfChildNodes, TreeNode):
            listOfChildNodes = [listOfChildNodes]
        assert isinstance(listOfChildNodes, list)
        l = len(listOfChildNodes)
        idxLast = index+l-1
        self.sigWillAddChildren.emit(self, index, idxLast)
        for i, node in enumerate(listOfChildNodes):
            assert isinstance(node, TreeNode)
            node.mParent = self
            # connect node signals
            node.sigWillAddChildren.connect(self.sigWillAddChildren)
            node.sigAddedChildren.connect(self.sigAddedChildren)
            node.sigWillRemoveChildren.connect(self.sigWillRemoveChildren)
            node.sigRemovedChildren.connect(self.sigRemovedChildren)
            node.sigUpdated.connect(self.sigUpdated)

            self.mChildren.insert(index+i, node)

        self.sigAddedChildren.emit(self, index, idxLast)

    def removeChildNode(self, node):
        assert node in self.mChildren
        i = self.mChildren.index(node)
        self.removeChildNodes(i, 1)

    def removeChildNodes(self, row, count):

        if row < 0 or count <= 0:
            return False

        rowLast = row + count - 1

        if rowLast >= self.childCount():
            return False

        self.sigWillRemoveChildren.emit(self, row, rowLast)
        to_remove = self.childNodes()[row:rowLast+1]
        for n in to_remove:
            self.mChildren.remove(n)
            #n.mParent = None

        self.sigRemovedChildren.emit(self, row, rowLast)



    def setToolTip(self, toolTip):
        self.mToolTip = toolTip
    def toolTip(self):
        return self.mToolTip

    def parentNode(self):
        return self.mParent

    def setParentNode(self, treeNode):
        assert isinstance(treeNode, TreeNode)
        self.mParent = treeNode

    def setIcon(self, icon):
        self.mIcon = icon

    def icon(self):
        return self.mIcon

    def setName(self, name):
        self.mName = name

    def name(self):
        return self.mName

    def contextMenu(self):
        return None


    def setValues(self, listOfValues):
        if not isinstance(listOfValues, list):
            listOfValues = [listOfValues]
        self.mValues = listOfValues[:]
    def values(self):
        return self.mValues[:]

    def childCount(self):
        return len(self.mChildren)

    def childNodes(self):
        return self.mChildren[:]

    def findChildNodes(self, type, recursive=True):
        results = []
        for node in self.mChildren:
            if isinstance(node, type):
                results.append(node)
            if recursive:
                results.extend(node.findChildNodes(type, recursive=True))
        return results


class SourceRasterBandNode(TreeNode):
    def __init__(self, parentNode, vrtRasterInputSourceBand):
        assert isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand)
        super(SourceRasterBandNode, self).__init__(parentNode)
        self.setIcon(QIcon(":/vrtbuilder/mIconRaster.png"))
        self.mSrcBand = vrtRasterInputSourceBand
        self.setName('{}:{}'.format(os.path.basename(self.mSrcBand.mPath), self.mSrcBand.mBandIndex + 1))
        self.setValues([self.mSrcBand.mBandName])
        self.setToolTip('band {}:{}'.format(self.mSrcBand.mBandIndex + 1, self.mSrcBand.mPath))


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
        node = VRTRasterBandNode(None, vrtRasterBand)
        self.insertChildNodes(i, [node])

    def onBandRemoved(self, removedIdx):
        self.removeChildNodes(removedIdx, 1)


class VRTRasterBandNode(TreeNode):
    def __init__(self, parentNode, virtualBand):
        assert isinstance(virtualBand, VRTRasterBand)

        super(VRTRasterBandNode, self).__init__(parentNode)
        self.mVirtualBand = virtualBand

        self.setName(virtualBand.name())
        self.setIcon(QIcon(":/vrtbuilder/mIconVirtualRaster.png"))
        # self.nodeBands = TreeNode(self, name='Input Bands')
        # self.nodeBands.setToolTip('Source bands contributing to this virtual raster band')
        self.nodeBands = self
        virtualBand.sigNameChanged.connect(self.setName)
        virtualBand.sigSourceInserted.connect(lambda _, src: self.onSourceInserted(src))
        virtualBand.sigSourceRemoved.connect(self.onSourceRemoved)
        for src in self.mVirtualBand.sources:
            self.onSourceInserted(src)

    def onSourceInserted(self, inputSource):
        assert isinstance(inputSource, VRTRasterInputSourceBand)
        assert inputSource.virtualBand() == self.mVirtualBand
        i = self.mVirtualBand.sources.index(inputSource)

        node = VRTRasterInputSourceBandNode(None, inputSource)
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
        self.setIcon(QIcon(":/vrtbuilder/mIconRaster.png"))
        self.mSrc = vrtRasterInputSourceBand
        name = '{}:{}'.format(os.path.basename(self.mSrc.mPath),self.mSrc.mBandIndex + 1)
        self.setName(name)
        # self.setValues([self.mSrc.mPath, self.mSrc.mBandIndex])

    def sourceBand(self):
        return self.mSrc




class VRTRasterVectorLayer(QgsVectorLayer):

    def __init__(self, vrtRaster, crs=None):
        assert isinstance(vrtRaster, VRTRaster)
        if crs is None:
            crs = QgsCoordinateReferenceSystem('EPSG:4326')

        uri = 'polygon?crs={}'.format(crs.authid())
        super(VRTRasterVectorLayer, self).__init__(uri, 'VRTRaster', 'memory', False)
        self.mCrs = crs
        self.mVRTRaster = vrtRaster

        #initialize fields
        assert self.startEditing()
        # standard field names, types, etc.
        fieldDefs = [('oid', QVariant.Int, 'integer'),
                     ('type', QVariant.String, 'string'),
                     ('name', QVariant.String, 'string'),
                     ('path', QVariant.String, 'string'),
                     ]
        # initialize fields
        for fieldDef in fieldDefs:
            field = QgsField(fieldDef[0], fieldDef[1], fieldDef[2])
            self.addAttribute(field)
        self.commitChanges()

        symbol = QgsFillSymbolV2.createSimple({'style': 'no', 'color': 'red', 'outline_color':'black'})
        self.rendererV2().setSymbol(symbol)
        self.label().setFields(self.fields())
        self.label().setLabelField(3,3)
        self.mVRTRaster.sigSourceRasterAdded.connect(self.onRasterInserted)
        self.mVRTRaster.sigSourceRasterRemoved.connect(self.onRasterRemoved)
        self.onRasterInserted(self.mVRTRaster.sourceRaster())

    def path2feature(self, path):
        for f in self.dataProvider().getFeatures():
            if str(f.attribute('path')) == str(path):
                return f
        return None

    def path2fid(self, path):
        for f in self.dataProvider().getFeatures():
            if str(f.attribute('path')) == str(path):
                return f.id()


        return None

    def fid2path(self, fid):
        for f in self.dataProvider().getFeatures():
            if f.fid() == fid:
                return f

        return None

    def onRasterInserted(self, listOfNewFiles):
        assert isinstance(listOfNewFiles, list)
        if len(listOfNewFiles) == 0:
            return
        self.startEditing()
        for f in listOfNewFiles:
            bounds = self.mVRTRaster.sourceRasterBounds()[f]
            assert isinstance(bounds, RasterBounds)
            oid = str(id(bounds))
            geometry =QgsPolygonV2(bounds.polygon)
            #geometry = QgsCircularStringV2(bounds.curve)
            trans = QgsCoordinateTransform(bounds.crs, self.crs())
            geometry.transform(trans)




            feature = QgsFeature(self.pendingFields())
            #feature.setGeometry(QgsGeometry(geometry))
            feature.setGeometry(QgsGeometry.fromWkt(geometry.asWkt()))
            #feature.setFeatureId(int(oid))
            feature.setAttribute('oid', oid)
            feature.setAttribute('type', 'source file')
            feature.setAttribute('name', str(os.path.basename(f)))
            feature.setAttribute('path', str(f))
            #feature.setValid(True)

            assert self.dataProvider().addFeatures([feature])
            self.featureAdded.emit(feature.id())


        self.updateExtents()
        assert self.commitChanges()
        self.dataChanged.emit()

    def onRasterRemoved(self, files):
        self.startEditing()
        self.selectAll()
        toRemove = []
        for f in self.selectedFeatures():
            if f.attribute('path') in files:
                toRemove.append(f.id())
        self.setSelectedFeatures(toRemove)
        self.deleteSelectedFeatures()
        self.commitChanges()
        self.dataChanged.emit()



class VRTRasterPreviewMapCanvas(QgsMapCanvas):

    def __init__(self, parent=None, *args, **kwds):
        super(VRTRasterPreviewMapCanvas, self).__init__(parent, *args, **kwds)
        self.setCrsTransformEnabled(True)

    def crs(self):
        return self.mapSettings().destinationCrs()

    def contextMenuEvent(self,  event):
        menu = QMenu()
        action = menu.addAction('Refresh')
        action.triggered.connect(self.refresh)

        action = menu.addAction('Reset')
        action.triggered.connect(self.reset)

        menu.exec_(event.globalPos())

    def setLayerSet(self, layers):
        raise DeprecationWarning()

    def setLayers(self, layers):
        assert isinstance(layers, list)
        def area(layer):
            extent = layer.extent()
            return extent.width() * extent.height()
        layers = list(sorted(layers, key = lambda lyr: area(lyr), reverse=True))
        QgsMapLayerRegistry.instance().addMapLayers(layers, False)

        super(VRTRasterPreviewMapCanvas, self).setLayerSet([QgsMapCanvasLayer(l) for l in layers])




    def reset(self):
        extent = self.fullExtent()
        extent.scale(1.05)
        self.setExtent(extent)
        self.refresh()


class SourceRasterFileNode(TreeNode):

    def __init__(self, parentNode, path):
        super(SourceRasterFileNode, self).__init__(parentNode)

        self.mPath = path
        self.setName(os.path.basename(path))
        srcNode = TreeNode(self, name='Path')
        srcNode.setValues(path)


        #populate metainfo
        ds = gdal.Open(path)
        assert isinstance(ds, gdal.Dataset)


        crsNode = TreeNode(self, name='CRS')
        crsNode.setIcon(QIcon(':/vrtbuilder/CRS.png'))
        crs = osr.SpatialReference()
        crs.ImportFromWkt(ds.GetProjection())

        authInfo = '{}:{}'.format(crs.GetAttrValue('AUTHORITY',0), crs.GetAttrValue('AUTHORITY',1))
        crsNode.setValues([authInfo,crs.ExportToWkt()])
        self.bandNode = TreeNode(None, name='Bands')
        for b in range(ds.RasterCount):
            band = ds.GetRasterBand(b+1)

            inputSource = VRTRasterInputSourceBand(path, b)
            inputSource.mBandName = band.GetDescription()
            if inputSource.mBandName in [None,'']:
                inputSource.mBandName = '{}'.format(b + 1)
            inputSource.mNoData = band.GetNoDataValue()

            SourceRasterBandNode(self.bandNode, inputSource)
        self.bandNode.setParentNode(self)
        self.appendChildNodes(self.bandNode)

    def sourceBands(self):
        return [n.mSrcBand for n in self.bandNode.mChildren if isinstance(n, SourceRasterBandNode)]

class TreeView(QTreeView):
    def __init__(self, *args, **kwds):
        super(TreeView, self).__init__(*args, **kwds)


class TreeModel(QAbstractItemModel):
    def __init__(self, parent=None, rootNode=None):
        super(TreeModel, self).__init__(parent)

        self.mColumnNames = ['Node', 'Value']
        self.mRootNode = rootNode if isinstance(rootNode, TreeNode) else TreeNode(None)
        self.mRootNode.sigWillAddChildren.connect(self.nodeWillAddChildren)
        self.mRootNode.sigAddedChildren.connect(self.nodeAddedChildren)
        self.mRootNode.sigWillRemoveChildren.connect(self.nodeWillRemoveChildren)
        self.mRootNode.sigRemovedChildren.connect(self.nodeRemovedChildren)
        self.mRootNode.sigUpdated.connect(self.nodeUpdated)

        self.mTreeView = None
        if isinstance(parent, QTreeView):
            self.connectTreeView(parent)

    def nodeWillAddChildren(self, node, idx1, idxL):
        idxNode = self.node2idx(node)
        self.beginInsertRows(idxNode, idx1, idxL)

    def nodeAddedChildren(self, node, idx1, idxL):
        self.endInsertRows()
        # for i in range(idx1, idxL+1):
        for n in node.childNodes():
            #self.setColumnSpan(node)
            pass

    def nodeWillRemoveChildren(self, node, idx1, idxL):
        idxNode = self.node2idx(node)
        self.beginRemoveRows(idxNode, idx1, idxL)

    def nodeRemovedChildren(self, node, idx1, idxL):
        self.endRemoveRows()

    def nodeUpdated(self, node):
        idxNode = self.node2idx(node)
        self.dataChanged.emit(idxNode, idxNode)
        self.setColumnSpan(node)

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:

            if len(self.mColumnNames) > section:
                return self.mColumnNames[section]
            else:
                return ''

        else:
            return None

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = self.idx2node(index)
        if not isinstance(node, TreeNode):
            return QModelIndex()

        parentNode = node.parentNode()
        if not isinstance(parentNode, TreeNode):
            return QModelIndex()

        return self.node2idx(parentNode)

        if node not in parentNode.mChildren:
            return QModelIndex
        row = parentNode.mChildren.index(node)
        return self.createIndex(row, 0, parentNode)

    def rowCount(self, index):

        node = self.idx2node(index)
        return len(node.mChildren) if isinstance(node, TreeNode) else 0

    def hasChildren(self, index):
        node = self.idx2node(index)
        return isinstance(node, TreeNode) and len(node.mChildren) > 0

    def columnNames(self):
        return self.mColumnNames

    def columnCount(self, index):

        return len(self.mColumnNames)

    def connectTreeView(self, treeView):
        self.mTreeView = treeView

    def setColumnSpan(self, node):
        if isinstance(self.mTreeView, QTreeView) \
                and isinstance(node, TreeNode) \
                and isinstance(node.parentNode(), TreeNode):
            idxNode = self.node2idx(node)
            idxParent = self.node2idx(node.parentNode())
            span = len(node.values()) == 0
            self.mTreeView.setFirstColumnSpanned(idxNode.row(), idxParent, span)
            for n in node.childNodes():
                self.setColumnSpan(n)

    def index(self, row, column, parentIndex=None):

        if parentIndex is None:
            parentNode = self.mRootNode
        else:
            parentNode = self.idx2node(parentIndex)

        if row < 0 or row >= parentNode.childCount():
            return QModelIndex()
        if column < 0 or column >= len(self.mColumnNames):
            return QModelIndex()

        if isinstance(parentNode, TreeNode) and row < len(parentNode.mChildren):
            return self.createIndex(row, column, parentNode.mChildren[row])
        else:
            return QModelIndex()

    def findParentNode(self, node, parentNodeType):
        assert isinstance(node, TreeNode)
        while True:
            if isinstance(node, parentNodeType):
                return node
            if not isinstance(node.parentNode(), TreeNode):
                return None
            node = node.parentNode()

    def indexes2nodes(self, indexes):
        assert isinstance(indexes, list)
        nodes = []
        for idx in indexes:
            n = self.idx2node(idx)
            if n not in nodes:
                nodes.append(n)
        return nodes

    def nodes2indexes(self, nodes):
        return [self.node2idx(n) for n in nodes]

    def idx2node(self, index):
        if not index.isValid():
            return self.mRootNode
        else:
            return index.internalPointer()

    def node2idx(self, node):
        assert isinstance(node, TreeNode)
        if node == self.mRootNode:
            return QModelIndex()
        else:
            parentNode = node.parentNode()
            assert isinstance(parentNode, TreeNode)
            if node not in parentNode.mChildren:
                return QModelIndex()
            r = parentNode.mChildren.index(node)
            return self.createIndex(r, 0, node)

    def data(self, index, role):
        node = self.idx2node(index)
        col = index.column()
        if role == Qt.UserRole:
            return node

        if col == 0:
            if role in [Qt.DisplayRole, Qt.EditRole]:
                return node.name()
            if role == Qt.DecorationRole:
                return node.icon()
            if role == Qt.ToolTipRole:
                return node.toolTip()
        if col > 0:
            i = col - 1

            if role in [Qt.DisplayRole, Qt.EditRole] and len(node.values()) > i:
                return node.values()[i]

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        node = self.idx2node(index)
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

class SourceRasterFilterModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super(SourceRasterFilterModel, self).__init__(parent)

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
            pattern = reg.pattern().replace(':','')
            reg.setPattern(pattern)

        return reg.indexIn(s0) >= 0 or reg.indexIn(s1) >= 0


    def filterAcceptsColumn(self, sourceColumn, sourceParent):
        node = self.sourceModel().idx2node(sourceParent)
        if not isinstance(node, SourceRasterBandNode):
            return True
        else:
            return sourceColumn in [0,1]

class SourceRasterModel(TreeModel):
    def __init__(self, parent=None):
        super(SourceRasterModel, self).__init__(parent)

        self.mColumnNames = ['File', 'Value']

    def files(self):
        return [n.mPath for n in self.mRootNode.childNodes() if isinstance(n, SourceRasterFileNode)]

    def addFile(self, file):
        self.addFiles([file])

    def addFiles(self, newFiles):
        assert isinstance(newFiles, list)
        existingFiles = self.files()
        newFiles = [os.path.normpath(f) for f in newFiles]
        newFiles = [f for f in newFiles if f not in existingFiles and isinstance(gdal.Open(f), gdal.Dataset)]
        if len(newFiles) > 0:
            for f in newFiles:
                SourceRasterFileNode(self.mRootNode, f)

    def file2node(self, file):
        for node in self.mRootNode.childNodes():
            if isinstance(node, SourceRasterFileNode) and node.mPath == file:
                return node
        return None

    def removeFiles(self, listOfFiles):
        assert isinstance(listOfFiles, list)

        toRemove = [n for n in self.mRootNode.childNodes() \
                    if isinstance(n, SourceRasterFileNode) and n.mPath in listOfFiles]

        for n in toRemove:
            n.parentNode().removeChildNode(n)

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        node = self.idx2node(index)

        flags = super(SourceRasterModel, self).flags(index)
        # return flags
        if isinstance(node, SourceRasterFileNode) or \
                isinstance(node, SourceRasterBandNode):
            flags |= Qt.ItemIsDragEnabled
        return flags

    def contextMenu(self):

        return None

    def mimeTypes(self):
        # specifies the mime types handled by this model
        types = []
        types.append('text/uri-list')
        return types

    def mimeData(self, indexes):
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
        uriList = [sourceBand.mPath for sourceBand in sourceBands]
        uriList = list(OrderedDict.fromkeys(uriList))

        mimeData = QMimeData()

        if len(sourceBands) > 0:
            mimeData.setData('hub.vrtbuilder/bandlist', pickle.dumps(sourceBands))

        # set text/uri-list
        if len(uriList) > 0:
            mimeData.setUrls([QUrl(p) for p in uriList])
            # mimeData.setText('\n'.join(uriList))
        return mimeData


class VRTSelectionModel(QItemSelectionModel):
    def __init__(self, model, mapCanvas, vectorLayer, parent=None):
        assert isinstance(model, VRTRasterTreeModel)
        assert isinstance(vectorLayer, VRTRasterVectorLayer)
        # assert isinstance(mapCanvas, VRTRasterPreviewMapCanvas)
        super(VRTSelectionModel, self).__init__(model, parent)
        self.mLyr = vectorLayer
        self.mPreviewMapHighlights = {}

        self.mLyr.featureDeleted.connect(lambda: self.setMapHighlights(None))
        self.mLyr.featureAdded.connect(lambda: self.setMapHighlights(None))
        self.mModel = model
        self.mCanvas = mapCanvas
        self.selectionChanged.connect(self.onTreeSelectionChanged)

        self.previewMapTool = QgsMapToolEmitPoint(self.mCanvas)
        self.previewMapTool.setCursor(Qt.ArrowCursor)
        self.previewMapTool.canvasClicked.connect(self.onMapFeatureIdentified)
        self.mCanvas.setMapTool(self.previewMapTool)

    @pyqtSlot(QgsFeature)
    def onMapFeatureIdentified(self, point, button):
        assert isinstance(point, QgsPoint)

        if self.sender() == self.previewMapTool:
            searchRadius = QgsTolerance.toleranceInMapUnits( \
                1, self.mLyr, self.mCanvas.mapRenderer(), QgsTolerance.Pixels)
            searchRect = QgsRectangle()
            searchRect.setXMinimum(point.x() - searchRadius);
            searchRect.setXMaximum(point.x() + searchRadius);
            searchRect.setYMinimum(point.y() - searchRadius);
            searchRect.setYMaximum(point.y() + searchRadius);

            crs = self.previewMapTool.canvas().crs()
            trans = QgsCoordinateTransform(crs, self.mLyr.crs())
            oldSelection = self.selectedSourceFiles()
            searchRect = trans.transform(searchRect)

            if button == Qt.LeftButton:
                """

                lastSelection = set([f.id() for f in lyr.selectedFeatures()])
                lyr.setSelectedFeatures([])
                lyr.select(rect, True)
                """
                # select the feature closet to the point
                selectedId = None
                if True:
                    geoms = {}
                    flags = QgsFeatureRequest.ExactIntersect
                    features = self.mLyr.getFeatures(QgsFeatureRequest() \
                                                     .setFilterRect(searchRect) \
                                                     .setFlags(flags))
                    feature = QgsFeature()
                    while features.nextFeature(feature):
                        geoms[feature.geometry().area()] = feature.id()

                    if len(geoms) > 0:
                        selectedId = geoms[min(geoms.keys())]

                modifiers = QApplication.keyboardModifiers()

                newSelection = set([selectedId])

                # todo: allow select modifiers to select more than one
                if modifiers & Qt.ControlModifier:
                    newSelection = oldSelection.difference(newSelection)
                elif modifiers & Qt.ShiftModifier:
                    newSelection = oldSelection.union(newSelection)

                newSelection = list(newSelection)
                self.setSelectedSourceFiles(newSelection)

    def onTreeSelectionChanged(self, selected, deselected):
        sourceFiles = self.selectedSourceFiles()
        features = set([self.mLyr.path2feature(path) for path in sourceFiles])
        self.setMapHighlights(features)

    def selectedSourceFileNodes(self):
        indexes = self.selectedIndexes()
        selectedFileNodes = self.mModel.indexes2nodes(indexes)
        return [n for n in selectedFileNodes if isinstance(n, VRTRasterInputSourceBandNode)]

    def selectedSourceFiles(self):
        return set(n.sourceBand().mPath for n in self.selectedSourceFileNodes())

    def setMapHighlights(self, features):
        if features is None:
            features = []
        for f in self.mPreviewMapHighlights.keys():
            if f not in features:
                del self.mPreviewMapHighlights[f]

        for f in features:
            if f not in self.mPreviewMapHighlights.keys():
                h = QgsHighlight(self.mCanvas, f.geometry(), self.mLyr)
                h.setColor(QColor(0, 255, 0, 255))
                h.setWidth(3)
                h.setFillColor(QColor(255, 0, 0, 0))
                self.mPreviewMapHighlights[f] = h

    def setSelectedSourceFiles(self, newSelection):
        ids = []
        paths = []
        features = []
        for f in self.mLyr.dataProvider().getFeatures(QgsFeatureRequest()):
            id = f.id()
            path = str(f.attribute('path'))

            if id in newSelection or path in newSelection:
                ids.append(id)
                paths.append(path)
                features.append(f)

        # set map overlay
        self.setMapHighlights(features)

        srcNodesAll = self.model().mRootNode.findChildNodes(
            VRTRasterInputSourceBandNode, recursive=True)

        nodeSelection = QItemSelection()
        # 1. select the nodes pointing to one of the source files
        for n in srcNodesAll:
            if n.sourceBand().mPath in paths:
                idx = self.model().node2idx(n)
                nodeSelection.select(idx, idx)
        # v = self.blockSignals(True)
        self.select(nodeSelection, QItemSelectionModel.SelectCurrent)
        # self.blockSignals(v)
        # self.model().select(self.model.node2idx(n), QItemSelectionModel.Select)


class VRTRasterTreeModel(TreeModel):
    def __init__(self, parent=None, vrtRaster=None):

        vrtRaster = vrtRaster if isinstance(vrtRaster, VRTRaster) else VRTRaster()
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

    def srcFileIndices(self, srcFile):
        srcFileNodes = self.mRootNode.findChildNodes(VRTRasterInputSourceBandNode, recursive=True)
        return self.nodes2indexes(srcFileNodes)

    def removeSources(self, sources):
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

    def dragEnterEvent(self, event):
        assert isinstance(event, QDragEnterEvent)
        if event.mimeData().hasFormat(u'hub.vrtbuilder/bandlist'):
            event.accept()

    def dragMoveEvent(self, event):
        assert isinstance(event, QDragMoveEvent)
        if event.mimeData().hasFormat(u'hub.vrtbuilder/bandlist'):
            event.accept()

    def dropEvent(self, event):
        assert isinstance(event, QDropEvent)

        if event.mimeData().hasFormat(u'hub.vrtbuilder/bandlist'):
            parent = self.mRootNode
            p = self.node2idx(parent)
            self.dropMimeData(event.mimeData(), event.dropAction(), 0, 0, p)

            event.accept()

        s = ""

    def mimeTypes(self):
        # specifies the mime types handled by this model
        types = []
        types.append('text/uri-list')
        types.append('hub.vrtbuilder/bandlist')
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
        uriList = [sourceBand.mPath for sourceBand in sourceBands]
        uriList = list(OrderedDict.fromkeys(uriList))

        mimeData = QMimeData()

        if len(sourceBands) > 0:
            mimeData.setData('hub.vrtbuilder/bandlist', pickle.dumps(sourceBands))

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

        if u'hub.vrtbuilder/bandlist' in mimeData.formats():
            dump = mimeData.data(u'hub.vrtbuilder/bandlist')
            sourceBands = pickle.loads(dump)

        elif u'hub.vrtbuilder/vrt.indices' in mimeData.formats():
            dump = mimeData.data(u'hub.vrtbuilder/vrt.indices')
            indices = pickle.loads(dump)
            s = ""

            if action == Qt.MoveAction:
                s = ""
        #drop files
        elif mimeData.hasUrls():
            for url in mimeData.urls():
                if url.isValid():
                    path = str(url.path())
                    if os.path.isfile(path):
                        sourceBands.extend(VRTRasterInputSourceBand.fromGDALDataSet(str(url.path())))

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

            #step 1: temporary storage by source image path
            sourceImages = {}
            for b in sourceBands:
                assert isinstance(b, VRTRasterInputSourceBand)
                if not b.mPath in sourceImages.keys():
                    sourceImages[b.mPath] = []
                sourceImages[b.mPath].append(b)
            for p in sourceImages.keys():
                sourceImages[p] = sorted(sourceImages[p], key=lambda b: b.mBandIndex)

            if len(sourceImages) == 0:
                return True

            #step 2: create the nested list



            sourceBands = []
            while len(sourceImages) > 0:
                sourceBands.append([])

                for k in sourceImages.keys():
                    sourceBands[-1].append(sourceImages[k].pop(0))
                    if len(sourceImages[k]) == 0:
                        del sourceImages[k]

        elif self.mDropMode == 'PURE_STACK':
            #pure stacking: each source band defines its own virtual band
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

        #add the source bands to the VRT
        for bands in sourceBands:
            iSrc = row
            for src in bands:
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
        self.sourceFileModel = SourceRasterModel(parent=self.treeViewSourceFiles)
        self.sourceFileProxyModel = SourceRasterFilterModel()
        self.sourceFileProxyModel.setSourceModel(self.sourceFileModel)
        self.tbSourceFileFilter.textChanged.connect(self.onSourceFileFilterChanged)
        self.cbSourceFileFilterRegex.clicked.connect(lambda : self.onSourceFileFilterChanged(self.tbSourceFileFilter.text()))
        #self.treeViewSourceFiles.setModel(self.sourceFileModel)
        self.treeViewSourceFiles.setModel(self.sourceFileProxyModel)

        self.mCrsManuallySet = False
        self.mBoundsManuallySet = False

        self.tbNoData.setValidator(QDoubleValidator())

        self.tbOutputPath.textChanged.connect(self.onOutputPathChanged)

        filter = 'GDAL Virtual Raster (*.vrt);;GeoTIFF (*.tiff *.tif);;ENVI (*.bsq *.bil *.bip)'
        self.btnSelectVRTPath.clicked.connect(lambda:
                                              self.tbOutputPath.setText(
                                                  QFileDialog.getSaveFileName(self,
                                                                              directory=self.tbOutputPath.text(),
                                                                              caption='Select output image',
                                                                              filter=filter)
                                              ))
        self.buttonBox.button(QDialogButtonBox.Save).clicked.connect(self.saveFile)
        self.vrtRaster = VRTRaster()
        self.vrtRasterLayer = VRTRasterVectorLayer(self.vrtRaster)
        self.vrtRasterLayer.dataChanged.connect(self.resetMap)
        self.vrtRaster.sigSourceRasterAdded.connect(self.sourceFileProxyModel.sourceModel().addFiles)
        self.mBackgroundLayer = None
        # self.vrtRasterLayer.editingStopped.connect(self.resetMap)


        assert isinstance(self.previewMap, QgsMapCanvas)

        self.previewMap.setLayers([self.vrtRasterLayer])
        self.resetMap()

        self.vrtRaster.sigCrsChanged.connect(self.updateSummary)
        self.vrtRaster.sigSourceBandInserted.connect(self.updateSummary)
        self.vrtRaster.sigSourceBandRemoved.connect(self.updateSummary)

        self.vrtRaster.sigBandInserted.connect(self.updateSummary)
        self.vrtRaster.sigBandRemoved.connect(self.updateSummary)

        self.vrtBuilderModel = VRTRasterTreeModel(parent=self.treeViewVRT, vrtRaster=self.vrtRaster)
        self.btnStackFiles.toggled.connect(lambda isChecked:
                                           self.vrtBuilderModel.setDropMode('PURE_STACK')
                                           if isChecked
                                           else self.vrtBuilderModel.setDropMode(('NESTED_STACK')))

        self.treeViewVRT.setModel(self.vrtBuilderModel)

        self.vrtTreeSelectionModel = VRTSelectionModel(
            self.treeViewVRT.model(),
            self.previewMap,
            self.vrtRasterLayer)

        self.vrtTreeSelectionModel.selectionChanged.connect(self.onVRTSelectionChanged)

        self.treeViewVRT.setSelectionModel(self.vrtTreeSelectionModel)

        # 2. expand the parent nodes
        self.treeViewVRT.setAutoExpandDelay(50)
        self.treeViewVRT.setDragEnabled(True)
        self.treeViewVRT.contextMenuEvent = self.vrtTreeViewContextMenuEvent

        #extents
        self.cbBoundsFromSourceFiles.clicked.connect(self.onExtentChanged)
        for tb in [self.tbBoundsXMin, self.tbBoundsXMax, self.tbBoundsYMin, self.tbBoundsYMax]:
            tb.textChanged.connect(self.onExtentChanged)
            tb.setValidator(QDoubleValidator(0.000000000000001, 999999999999999999999, 20))

        #todo. set extent from map or other file

        #resolution settings
        self.cbResolution.currentIndexChanged.connect(self.onResolutionChanged)

        for tb in [self.tbResolutionX, self.tbResolutionY]:
            tb.setValidator(QDoubleValidator(0.000000000000001, 999999999999999999999, 5))
            tb.textChanged.connect(self.onResolutionChanged)
        self.cbResolution.setCurrentIndex(2) #== average resolution

        #todo: self.btnResFromFile.clicked.connect()

        #resampling settings
        from virtualrasters import LUT_ResampleAlgs
        self.cbResampling.clear()
        for k, v in LUT_ResampleAlgs.items():
            self.cbResampling.addItem(k, v)

        self.cbResampling.currentIndexChanged.connect(lambda :
                                                      self.vrtRaster.setResamplingAlg(
                                                          self.cbResampling.currentText()
                                                      ))
        self.vrtRaster.sigResamplingAlgChanged.connect(lambda alg:
                                                       self.cbResampling.setCurrentIndex(LUT_ResampleAlgs.keys().index(str(alg))))

        self.btnExpandAllVRT.clicked.connect(lambda: self.expandSelectedNodes(self.treeViewVRT, True))
        self.btnCollapseAllVRT.clicked.connect(lambda: self.expandSelectedNodes(self.treeViewVRT, False))

        self.btnExpandAllSrc.clicked.connect(lambda: self.expandSelectedNodes(self.treeViewSourceFiles, True))
        self.btnCollapseAllSrc.clicked.connect(lambda: self.expandSelectedNodes(self.treeViewSourceFiles, False))

        self.btnAddVirtualBand.clicked.connect(
            lambda: self.vrtRaster.addVirtualBand(VRTRasterBand(name='Band {}'.format(len(self.vrtRaster) + 1))))
        self.btnRemoveVirtualBands.clicked.connect(lambda: self.vrtBuilderModel.removeNodes(
            self.vrtBuilderModel.indexes2nodes(self.treeViewVRT.selectedIndexes())
        )
                                                   )
        self.btnLoadVRT.clicked.connect(lambda:
                                        self.vrtRaster.loadVRT(
                                            str(QFileDialog.getOpenFileName(self, "Open VRT file",
                                                                            filter='GDAL Virtual Raster (*.vrt)',
                                                                            directory=''))
                                        )
                                        )

        self.btnAbout.clicked.connect(lambda : AboutWidget(self).exec_())

        self.btnAddFromRegistry.clicked.connect(self.loadSrcFromMapLayerRegistry)
        self.btnAddSrcFiles.clicked.connect(lambda:
                                            self.sourceFileModel.addFiles(
                                                QFileDialog.getOpenFileNames(self, "Open raster images",
                                                                             directory='')
                                            ))

        self.btnRemoveSrcFiles.clicked.connect(lambda: self.sourceFileModel.removeFiles(
            [n.mPath for n in self.selectedSourceFileNodes()]
        ))

        self.mQgsProjectionSelectionWidget.dialog().setMessage('Set VRT CRS')
        self.mQgsProjectionSelectionWidget.crsChanged.connect(self.vrtRaster.setCrs)

        self.restoreLastSettings()

    def onSourceFileFilterChanged(self, text):

        useRegex = self.cbSourceFileFilterRegex.isChecked()
        if useRegex:
            self.sourceFileProxyModel.setFilterRegExp(text)
        else:
            self.sourceFileProxyModel.setFilterWildcard(text)

        pass

    def onExtentChanged(self,*args):

        if not self.frameExtent.isEnabled():
            self.vrtRaster.setExtent(None)
        else:
            values = [tb.text() for tb in [self.tbBoundsXMin, self.tbBoundsYMin, self.tbBoundsXMax, self.tbBoundsYMax]]
            if '' not in values:
                values = [float(v) for v in values]
                rectangle = QgsRectangle(*values)
                self.vrtRaster.setExtent(rectangle)

    def validateInputs(self):

        isValid = True
        self.buttonBox.button(QDialogButtonBox.Save).setEnabled(isValid)

    def onResolutionChanged(self, *args):

        mode = str(self.cbResolution.currentText())
        isUserMode = mode == 'user'
        self.frameUserResolution.setEnabled(isUserMode)
        self.validateInputs()
        if isUserMode:
            x = str(self.tbResolutionX.text())
            y = str(self.tbResolutionY.text())
            if len(x) > 0 and len(y) > 0:
                x = float(x)
                y = float(y)
                self.vrtRaster.setResolution(QSizeF(x,y))
        else:
            self.vrtRaster.setResolution(mode)

    def restoreDefaultSettings(self):
        self.cbAddtoMap.setChecked(True)
        self.cbCRSFromInputData.setChecked(True)
        from os.path import expanduser
        self.tbOutputPath.setText(os.path.join(expanduser('~'),'output.vrt'))
        self.cbBoundsFromSourceFiles.setChecked(True)
        self.saveSettings()

    def saveSettings(self):
        from vrtbuilder.utils import settings
        settings = settings()
        assert isinstance(settings, QSettings)
        settings.setValue('PATH_SAVE', self.tbOutputPath.text())
        settings.setValue('CRS_FROM_INPUT_DATA', self.cbCRSFromInputData.isChecked())
        settings.setValue('AUTOMATIC_BOUNDS', self.cbBoundsFromSourceFiles.isChecked())

    def restoreLastSettings(self):
        from vrtbuilder.utils import settings
        settings = settings()
        assert isinstance(settings, QSettings)
        from os.path import expanduser
        self.tbOutputPath.setText(settings.value('PATH_SAVE', os.path.join(expanduser('~'),'output.vrt')))
        self.cbCRSFromInputData.setChecked(bool(settings.value('CRS_FROM_INPUT_DATA', True)))
        self.cbBoundsFromSourceFiles.setChecked(bool(settings.value('AUTOMATIC_BOUNDS', True)))
        s = ""



    def resetMap(self, *args):

        lyrs = [self.vrtRasterLayer]
        if isinstance(self.mBackgroundLayer, QgsMapLayer):
            lyrs.insert(0, self.mBackgroundLayer)

        if lyrs != self.previewMap.layers():
            self.previewMap.setLayers(lyrs)
        self.previewMap.reset()

    def onVRTSelectionChanged(self, selected, deselected):
        self.btnRemoveVirtualBands.setEnabled(selected.count() > 0)
        # 2. expand the parent nodes
        model = self.vrtBuilderModel
        nodes = [model.idx2node(idx) for idx in selected.indexes()]
        selected = set([model.node2idx(n.parentNode()) for n in nodes if isinstance(n, VRTRasterInputSourceBandNode)])
        for idx in selected:
            self.treeViewVRT.expand(idx)

    def loadSrcFromMapLayerRegistry(self):
        reg = QgsMapLayerRegistry.instance()
        sources = set(lyr.source() for lyr in reg.mapLayers().values() if isinstance(lyr, QgsRasterLayer))
        sources = list(sources)
        sources = sorted(sources, key = lambda s : os.path.basename(s))
        for s in sources:
            self.sourceFileModel.addFile(s)

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

    def setBackgroundLayer(self, mapLayer):
        self.mBackgroundLayer = mapLayer
        self.resetMap()

    def saveFile(self):
        path = str(self.tbOutputPath.text())
        ext = os.path.splitext(path)[-1]

        saveBinary = ext != '.vrt'
        if saveBinary:
            pathVrt = path + '.vrt'
            self.vrtRaster.saveVRT(pathVrt)
        else:
            pathVrt = path
            self.vrtRaster.saveVRT(pathVrt)

        self.sigRasterCreated.emit(path)
        self.saveSettings()

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

    def addSourceFiles(self, files):
        """
        Adds a list of source files to the source file list.
        :param files: list-of-file-paths
        """
        self.sourceFileModel.addFiles(files)

    def updateSummary(self):

        self.tbSourceFileCount.setText('{}'.format(len(self.vrtRaster.sourceRaster())))
        self.tbVRTBandCount.setText('{}'.format(len(self.vrtRaster)))

        crs = self.vrtRaster.crs()
        if isinstance(crs, QgsCoordinateReferenceSystem):
            self.previewMap.setDestinationCrs(crs)
            if crs != self.mQgsProjectionSelectionWidget.crs():
                self.mQgsProjectionSelectionWidget.setCrs(crs)
        self.previewMap.refresh()

    def vrtTreeViewContextMenuEvent(self, event):

        idx = self.treeViewVRT.indexAt(event.pos())
        if not idx.isValid():
            pass

        selectedNodes = self.vrtBuilderModel.indexes2nodes(self.treeViewVRT.selectedIndexes())
        menu = QMenu(self.treeViewVRT)
        a = menu.addAction('Remove bands')
        a.setToolTip('Remove selected nodes')
        a.triggered.connect(lambda: self.vrtBuilderModel.removeNodes(selectedNodes))

        srcFiles = set()
        for n in selectedNodes:
            if isinstance(n, VRTRasterInputSourceBandNode):
                srcFiles.add(n.sourceBand().mPath)

        if len(srcFiles) > 0:
            a = menu.addAction('Remove sources')
            a.setToolTip('Remove all bands from selected source files.')
            a.triggered.connect(lambda: self.vrtBuilderModel.removeSources(srcFiles))

        menu.exec_(self.treeViewVRT.viewport().mapToGlobal(event.pos()))
        """
        if (menu & & menu->actions().count() != 0 )
        menu->exec (mapToGlobal(event->pos() ) );
        delete
        menu;
        """

    def mapReset(self):

        self.previewMap.refresh()
        self.vrtRasterLayer.setSelectedFeatures([])

        s = ""

if __name__ == '__main__':
    app = QApplication([])
    w = AboutWidget()
    w.show()
    app.exec_()