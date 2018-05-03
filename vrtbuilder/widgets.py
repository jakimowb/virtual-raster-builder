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

from vrtbuilder.models import TreeModel, TreeNode, TreeView
from vrtbuilder.virtualrasters import VRTRaster, VRTRasterBand, VRTRasterInputSourceBand, RasterBounds, RESAMPLE_ALGS
from vrtbuilder.utils import loadUi


LUT_FILEXTENSIONS = {}

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


class SourceRasterBandNode(TreeNode):
    def __init__(self, parentNode, vrtRasterInputSourceBand):
        assert isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand)
        super(SourceRasterBandNode, self).__init__(parentNode)
        self.setIcon(QIcon(":/vrtbuilder/mIconRaster.svg"))
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
        self.setIcon(QIcon(":/vrtbuilder/mIconVirtualRaster.svg"))
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
        self.setIcon(QIcon(":/vrtbuilder/mIconRaster.svg"))
        self.mSrc = vrtRasterInputSourceBand
        name = '{}:{}'.format(os.path.basename(self.mSrc.mPath), self.mSrc.mBandIndex + 1)
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
        super(VRTRasterVectorLayer, self).__init__(uri, 'VRTRaster', 'memory')
        self.mCrs = crs
        self.mVRTRaster = vrtRaster

        # initialize fields
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

        symbol = QgsFillSymbol.createSimple({'style': 'no', 'color': 'red', 'outline_color': 'black'})
        self.renderer().setSymbol(symbol)

        #self.mLabeling = QgsVectorLayerSimpleLabeling(self)

        #self.label().setFields(self.fields())
        #self.label().setLabelField(3, 3)
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
            geometry = QgsPolygon(bounds.polygon)

            trans = QgsCoordinateTransform()
            trans.setSourceCrs(bounds.crs)
            trans.setDestinationCrs(self.crs())

            geometry.transform(trans)

            feature = QgsFeature(self.fields())
            # feature.setGeometry(QgsGeometry(geometry))
            feature.setGeometry(QgsGeometry.fromWkt(geometry.asWkt()))
            # feature.setFeatureId(int(oid))
            feature.setAttribute('oid', oid)
            feature.setAttribute('type', 'source file')
            feature.setAttribute('name', str(os.path.basename(f)))
            feature.setAttribute('path', str(f))
            # feature.setValid(True)

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
        #self.setCrsTransformEnabled(True)

    def crs(self):
        return self.mapSettings().destinationCrs()

    def contextMenuEvent(self, event):
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

        layers = list(sorted(layers, key=lambda lyr: area(lyr), reverse=True))

        QgsProject.instance().addMapLayers(layers, False)
        #QgsMapLayerRegistry.instance().addMapLayers(layers, False)

        #super(VRTRasterPreviewMapCanvas, self).setLayerSet([QgsMapCanvasLayer(l) for l in layers])
        super(VRTRasterPreviewMapCanvas, self).setLayers(layers)

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

        # populate metainfo
        ds = gdal.Open(path)
        assert isinstance(ds, gdal.Dataset)

        crsNode = TreeNode(self, name='CRS')
        crsNode.setIcon(QIcon(':/vrtbuilder/CRS.svg'))
        #crs = osr.SpatialReference()
        #crs.ImportFromWkt(ds.GetProjection())
        #QgsCoordinateReferenceSystem(ds.GetProjection())
        #authInfo = '{}:{}'.format(crs.GetAttrValue(str('AUTHORITY'), 0), crs.GetAttrValue(str('AUTHORITY'), 1))
        crs = QgsCoordinateReferenceSystem(ds.GetProjection())
        authInfo = crs.authid()
        #crsNode.setValues([authInfo, crs.ExportToWkt()])
        crsNode.setValues([authInfo, crs.toWkt()])
        self.bandNode = TreeNode(None, name='Bands')
        for b in range(ds.RasterCount):
            band = ds.GetRasterBand(b + 1)

            inputSource = VRTRasterInputSourceBand(path, b)
            inputSource.mBandName = band.GetDescription().encode('utf-8')
            if inputSource.mBandName in [None, '']:
                inputSource.mBandName = '{}'.format(b + 1)
            inputSource.mNoData = band.GetNoDataValue()

            SourceRasterBandNode(self.bandNode, inputSource)
        self.bandNode.setParentNode(self)
        self.appendChildNodes(self.bandNode)

    def sourceBands(self):
        return [n.mSrcBand for n in self.bandNode.mChildren if isinstance(n, SourceRasterBandNode)]



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
    sigFilesAdded = pyqtSignal(list)
    sigFilesRemoved = pyqtSignal(list)

    def __init__(self, parent=None):
        super(SourceRasterModel, self).__init__(parent)

        self.mColumnNames = ['File/Band', 'Value/Description']


    def __len__(self):
        return len(self.files())


    def __iter__(self):
        return iter(self.files())


    def __contains__(self, file):
        return file in self.files()


    def files(self):
        return [n.mPath for n in self.mRootNode.childNodes() if isinstance(n, SourceRasterFileNode)]

    def addFile(self, file):
        self.addFiles([file])

    def addFiles(self, files):
        assert isinstance(files, list)
        existingFiles = self.files()
        newFiles = []

        for path in [os.path.normpath(f) for f in files]:
            ds = gdal.Open(path)
            if isinstance(ds, gdal.Dataset):
                nb = ds.RasterCount
                subs = [os.path.abspath(tup[0]) for tup in ds.GetSubDatasets()]

                if nb > 0:
                    newFiles.append(os.path.abspath(path))
                if len(subs) > 0:
                    newFiles.extend(subs)

        newFiles = [f for f in newFiles if f not in existingFiles and isinstance(gdal.Open(f), gdal.Dataset)]

        if len(newFiles) > 0:
            for f in newFiles:
                SourceRasterFileNode(self.mRootNode, f)
            self.sigFilesAdded.emit(newFiles)

    def file2node(self, file):
        for node in self.mRootNode.childNodes():
            if isinstance(node, SourceRasterFileNode) and node.mPath == file:
                return node
        return None

    def removeFiles(self, listOfFiles):
        assert isinstance(listOfFiles, list)

        toRemove = [n for n in self.mRootNode.childNodes() \
                    if isinstance(n, SourceRasterFileNode) and n.mPath in listOfFiles]
        if len(toRemove) > 0:
            for n in toRemove:
                n.parentNode().removeChildNode(n)
            self.sigFilesRemoved.emit(toRemove)

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
            paths = [url2path(url) for url in mimeData.urls()]
            paths = [p for p in paths if p is not None]
            self.addFiles(paths)
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

            self.addFiles(paths)
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


    def onMapFeatureIdentified(self, point, button):
        if not isinstance(point, QgsPoint):
            point = QgsPoint(point)
        assert isinstance(point, QgsPoint)

        if self.sender() == self.previewMapTool:
            searchRadius = QgsTolerance.toleranceInMapUnits( \
                1, self.mLyr, self.mCanvas.mapSettings(), QgsTolerance.Pixels)
            searchRect = QgsRectangle()
            searchRect.setXMinimum(point.x() - searchRadius);
            searchRect.setXMaximum(point.x() + searchRadius);
            searchRect.setYMinimum(point.y() - searchRadius);
            searchRect.setYMaximum(point.y() + searchRadius);

            crs = self.previewMapTool.canvas().crs()
            trans = QgsCoordinateTransform()
            trans.setSourceCrs(crs)
            trans.setDestinationCrs(self.mLyr.crs())

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
        for f in list(self.mPreviewMapHighlights.keys()):
            if f not in features:
                del self.mPreviewMapHighlights[f]

        for f in features:
            if f not in list(self.mPreviewMapHighlights.keys()):
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

    """
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
    """

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
        # drop files
        elif mimeData.hasUrls():
            for url in mimeData.urls():
                url = url2path(url)
                if url is not None:
                    sourceBands.extend(VRTRasterInputSourceBand.fromGDALDataSet(url))

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
                if not b.mPath in sourceImages.keys():
                    sourceImages[b.mPath] = []
                sourceImages[b.mPath].append(b)
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


class MapToolSpatialExtent(QgsMapToolEmitPoint):
    sigSpatialExtentSelected = pyqtSignal(QgsRectangle, QgsCoordinateReferenceSystem)

    def __init__(self, canvas):
        self.mCanvas = canvas
        QgsMapToolEmitPoint.__init__(self, self.mCanvas)
        self.mRubberBand = QgsRubberBand(self.mCanvas, 3)
        self.mRubberBand.setColor(Qt.red)
        self.mRubberBand.setFillColor(Qt.transparent)
        self.mRubberBand.setWidth(1)

        self.reset()

    def reset(self):
        self.startPoint = self.endPoint = None
        self.isEmittingPoint = False
        self.mRubberBand.reset(3)

    def canvasPressEvent(self, e):
        self.startPoint = self.toMapCoordinates(e.pos())
        self.endPoint = self.startPoint
        self.isEmittingPoint = True
        self.showRect(self.startPoint, self.endPoint)

    def canvasReleaseEvent(self, e):
        self.isEmittingPoint = False

        crs = self.mCanvas.mapSettings().destinationCrs()
        rect = self.rectangle()

        self.reset()
        if crs is not None and rect is not None:
            self.sigSpatialExtentSelected.emit(rect, crs)

    def canvasMoveEvent(self, e):

        if not self.isEmittingPoint:
            return

        self.endPoint = self.toMapCoordinates(e.pos())
        self.showRect(self.startPoint, self.endPoint)

    def showRect(self, startPoint, endPoint):
        #self.mRubberBand.reset(QgsWkbTypes.Polygon)
        self.mRubberBand.reset(3)
        if startPoint.x() == endPoint.x() or startPoint.y() == endPoint.y():
            return

        point1 = QgsPointXY(startPoint.x(), startPoint.y())
        point2 = QgsPointXY(startPoint.x(), endPoint.y())
        point3 = QgsPointXY(endPoint.x(), endPoint.y())
        point4 = QgsPointXY(endPoint.x(), startPoint.y())

        self.mRubberBand.addPoint(point1, False)
        self.mRubberBand.addPoint(point2, False)
        self.mRubberBand.addPoint(point3, False)
        self.mRubberBand.addPoint(point4, False)  # true to update canvas
        self.mRubberBand.closePoints(doUpdate=True)
        self.mRubberBand.show()

    def rectangle(self):
        if self.startPoint is None or self.endPoint is None:
            return None
        elif self.startPoint.x() == self.endPoint.x() or self.startPoint.y() == self.endPoint.y():

            return None

        return QgsRectangle(self.startPoint, self.endPoint)

        # def deactivate(self):
        #   super(RectangleMapTool, self).deactivate()
        # self.deactivated.emit()


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
            print(pathHTML)
            self.webView.load(QUrl.fromLocalFile(QFileInfo(pathHTML).absoluteFilePath()))



        else:
            self.tabHelp.setVisible(False)
            info = 'Unable to find help index.html'
            QgsApplication.instance().messageLog().logMessage(info)

        self.sourceFileModel = SourceRasterModel(parent=self.treeViewSourceFiles)
        self.sourceFileModel.sigFilesRemoved.connect(self.onSourceFilesChanged)
        self.sourceFileModel.sigFilesAdded.connect(self.onSourceFilesChanged)

        self.sourceFileProxyModel = SourceRasterFilterModel()
        self.sourceFileProxyModel.setSourceModel(self.sourceFileModel)

        self.tbSourceFileFilter.textChanged.connect(self.onSourceFileFilterChanged)
        self.cbSourceFileFilterRegex.clicked.connect(
            lambda: self.onSourceFileFilterChanged(self.tbSourceFileFilter.text()))
        # self.treeViewSourceFiles.setModel(self.sourceFileModel)

        assert isinstance(self.treeViewSourceFiles, QTreeView)
        self.treeViewSourceFiles.setModel(self.sourceFileProxyModel)
        self.treeViewSourceFiles.setDragEnabled(True)
        self.treeViewSourceFiles.setAcceptDrops(True)
        self.treeViewSourceFiles.setDropIndicatorShown(True)

        def onDragEnter(event):
            assert isinstance(event, QDragEnterEvent)
            supported = self.sourceFileModel.mimeTypes()
            for f in event.mimeData().formats():
                if f in supported:
                    event.acceptProposedAction()

        self.treeViewSourceFiles.dragEnterEvent = onDragEnter
        selectionModel = self.treeViewSourceFiles.selectionModel()

        #self.treeViewSourceFiles.dropEvent = onDropEvent
        #self.treeViewSourceFiles.supportedDropAction = onSupportedDropActions

        def fileDialogResult2Files(res):
            files, filter = res
            return files

        self.btnAddFromRegistry.clicked.connect(self.loadSrcFromMapLayerRegistry)
        self.btnAddSrcFiles.clicked.connect(lambda:
                                            self.sourceFileModel.addFiles(
                                                fileDialogResult2Files(
                                                    QFileDialog.getOpenFileNames(self, "Open raster images",
                                                                                 directory='')
                                                )
                                            ))

        self.btnRemoveSrcFiles.setDefaultAction(self.actionRemoveSourceFiles)

        def onRemoveSelectedSourceFiles():
            sm = self.treeViewSourceFiles.selectionModel()

            s = ""
            #self.sourceFileModel.removeFiles(    [n.mPath for n in self.selectedSourceFileNodes()]


        self.mCrsManuallySet = False
        self.mBoundsManuallySet = False

        self.tbNoData.setValidator(QDoubleValidator())

        filter = 'GDAL Virtual Raster (*.vrt);;GeoTIFF (*.tiff *.tif);;ENVI (*.bsq *.bil *.bip)'

        self.mQgsFileWidget.setFilter(filter)
        self.mQgsFileWidget.setStorageMode(QgsFileWidget.SaveFile)
        self.mQgsFileWidget.fileChanged.connect(self.onOutputPathChanged)

        self.buttonBox.button(QDialogButtonBox.Save).clicked.connect(self.saveFile)
        self.vrtRaster = VRTRaster()
        self.vrtRasterLayer = VRTRasterVectorLayer(self.vrtRaster)
        self.vrtRasterLayer.dataChanged.connect(self.resetMap)
        self.vrtRasterLayer.dataChanged.connect(self.validateInputs)
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

        # extents
        self.cbBoundsFromSourceFiles.clicked.connect(self.onExtentChanged)
        self.cbBoundsFromSourceFiles.clicked.connect(self.actionSelectSpatialExtent.setDisabled)
        self.cbBoundsFromSourceFiles.clicked.connect(self.frameExtent.setDisabled)
        self.cbBoundsFromSourceFiles.clicked.connect(self.btnBoundsFromFile.setDisabled)

        self.actionSelectSpatialExtent.setEnabled(not self.cbBoundsFromSourceFiles.isChecked())

        self.btnSelectSubset.setDefaultAction(self.actionSelectSpatialExtent)
        self.btnBoundsFromMap.setDefaultAction(self.actionSelectSpatialExtent)

        for tb in [self.tbBoundsXMin, self.tbBoundsXMax, self.tbBoundsYMin, self.tbBoundsYMax]:
            tb.textChanged.connect(self.onExtentChanged)
            tb.setValidator(QDoubleValidator(-999999999999999999999.0, 999999999999999999999.0, 20))

        self.btnBoundsFromFile.clicked.connect(
            lambda: self.setBoundsFromFile(str(QFileDialog.getOpenFileName(self, "Select raster file",
                                                                           directory=''))
                                           ))

        # resolution settings

        for tb in [self.tbResolutionX, self.tbResolutionY]:
            tb.setValidator(QDoubleValidator(0.000000000000001, 999999999999999999999, 5))
            tb.textChanged.connect(self.onResolutionChanged)
        self.cbResolution.setCurrentIndex(0)  # == average resolution

        self.btnResFromFile.clicked.connect(
            lambda: self.setResolutionFrom(fileDialogResult2Files(
                QFileDialog.getOpenFileName(self, "Select raster file",
                directory=''))
                              ))

        # todo: self.btnResFromFile.clicked.connect()

        self.cbResampling.clear()
        self.cbResampling.setModel(RESAMPLE_ALGS)
        self.cbResampling.currentIndexChanged.connect(lambda:
                                                      self.vrtRaster.setResamplingAlg(
                                                          self.cbResampling.currentData().mValue
                                                      ))
        self.vrtRaster.sigResamplingAlgChanged[int].connect(lambda alg:
                                                       self.cbResampling.setCurrentIndex(
                                                           RESAMPLE_ALGS.optionValues().index(alg)))

        self.btnExpandAllVRT.clicked.connect(lambda: self.expandSelectedNodes(self.treeViewVRT, True))
        self.btnCollapseAllVRT.clicked.connect(lambda: self.expandSelectedNodes(self.treeViewVRT, False))

        self.btnExpandAllSrc.clicked.connect(lambda: self.expandSelectedNodes(self.treeViewSourceFiles, True))
        self.btnCollapseAllSrc.clicked.connect(lambda: self.expandSelectedNodes(self.treeViewSourceFiles, False))

        self.btnAddVirtualBand.clicked.connect(
            lambda: self.vrtRaster.addVirtualBand(VRTRasterBand(name='Band {}'.format(len(self.vrtRaster) + 1))))
        self.btnRemoveVirtualBands.clicked.connect(lambda: self.vrtBuilderModel.removeNodes(
            self.vrtBuilderModel.indexes2nodes(self.treeViewVRT.selectedIndexes())
        ))

        self.btnLoadVRT.setDefaultAction(self.actionLoadVRT)

        self.btnAbout.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        self.btnAbout.clicked.connect(lambda: AboutWidget(self).exec_())


        self.mQgsProjectionSelectionWidget.setMessage('Set VRT CRS')
        self.mQgsProjectionSelectionWidget.crsChanged.connect(self.vrtRaster.setCrs)

        self.btnZoomIn.clicked.connect(lambda: self.activateMapTool('ZOOM_IN'))
        self.btnZoomOut.clicked.connect(lambda: self.activateMapTool('ZOOM_OUT'))
        self.btnPan.clicked.connect(lambda: self.activateMapTool('PAN'))
        self.btnZoomExtent.clicked.connect(lambda: self.previewMap.setExtent(self.previewMap.fullExtent()))

        self.actionSelectSpatialExtent.triggered.connect(lambda: self.activateMapTool('SELECT_EXTENT'))

        self.actionLoadVRT.triggered.connect(lambda:
                                        self.loadVRT(
                                            fileDialogResult2Files(
                                            QFileDialog.getOpenFileName(self, "Open VRT file",
                                                                            filter='GDAL Virtual Raster (*.vrt)',
                                                                            directory='')
                                            )
                                        )
                                        )

        self.cbResolution.currentIndexChanged.connect(self.onResolutionChanged)
        self.onResolutionChanged()

        self.mMapTools = {}
        self.initMapTools(self.previewMap)

        self.restoreLastSettings()
        self.validateInputs()

    def loadVRT(self, path):
        if path is not None and os.path.isfile(path):
            self.vrtRaster.loadVRT(path)

    def initMapTools(self, mapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)

        def addTools(key, tools):
            if not isinstance(tools, list):
                tools = [tools]

            if not key in self.mMapTools.keys():
                self.mMapTools[key] = []

            self.mMapTools[key].extend(tools)
            return tools

        addTools('ZOOM_IN', QgsMapToolZoom(mapCanvas, False))
        addTools('ZOOM_OUT', QgsMapToolZoom(mapCanvas, True))
        addTools('PAN', QgsMapToolPan(mapCanvas))

        for t in addTools('SELECT_EXTENT', MapToolSpatialExtent(mapCanvas)):
            t.sigSpatialExtentSelected.connect(self.setBounds)

    def activateMapTool(self, name):
        if name in self.mMapTools.keys():
            for t in self.mMapTools[name]:
                t.canvas().setMapTool(t)

    def onSourceFileFilterChanged(self, text):

        useRegex = self.cbSourceFileFilterRegex.isChecked()
        if useRegex:
            self.sourceFileProxyModel.setFilterRegExp(text)
        else:
            self.sourceFileProxyModel.setFilterWildcard(text)

        pass

    def setBounds(self, bbox, crs):
        assert isinstance(bbox, QgsRectangle)
        assert isinstance(crs, QgsCoordinateReferenceSystem)

        if not isinstance(self.vrtRaster.crs(), QgsCoordinateReferenceSystem):
            self.vrtRaster.setCrs(crs)

        if isinstance(crs, QgsCoordinateReferenceSystem) \
                and isinstance(self.vrtRaster.crs(), QgsCoordinateReferenceSystem):
            trans = QgsCoordinateTransform()
            trans.setSourceCrs(crs)
            trans.setDestinationCrs(self.vrtRaster.crs())
            bbox = trans.transform(bbox)

        self.tbBoundsXMin.setText('{}'.format(bbox.xMinimum()))
        self.tbBoundsXMax.setText('{}'.format(bbox.xMaximum()))
        self.tbBoundsYMin.setText('{}'.format(bbox.yMinimum()))
        self.tbBoundsYMax.setText('{}'.format(bbox.yMaximum()))

        self.vrtRaster.setExtent(bbox, crs)

        self.validateInputs()

    def setBoundsFromFile(self, file):
        if os.path.isfile(file) and gdal.Open(file) is gdal.Dataset:
            bounds = RasterBounds(file)
            bbox = bounds.polygon.boundingBox()
            self.setBounds(bbox, bounds.crs)

    def setResolutionFrom(self, file):
        if os.path.isfile(file) and isinstance(gdal.Open(file), gdal.Dataset):
            ds = gdal.Open(file)
            if isinstance(ds, gdal.Dataset):
                gt = ds.GetGeoTransform()
                res = QSizeF(abs(gt[1]), abs(gt[5]))
                # self.vrtRaster.setResolution()
                self.tbResolutionX.setText('{}'.format(res.width()))
                self.tbResolutionY.setText('{}'.format(res.height()))

            self.validateInputs()
            self.addSourceFile(file)

    def onSourceFilesChanged(self, *args):

        files = self.sourceFileModel.files()
        # refresh menu to select image bounds & image resolutions
        menuBounds = QMenu()
        menuResolution = QMenu()

        import qgis.utils
        if isinstance(qgis.utils.iface, QgisInterface) and \
             isinstance(qgis.utils.iface.mapCanvas(), QgsMapCanvas):
            a = menuBounds.addAction('QGIS MapCanvas')
            a.setToolTip('Use spatial extent of QGIS map canvas.')
            a.triggered.connect(lambda : self.setBounds(
                qgis.utils.iface.mapCanvas().extent(),
                qgis.utils.iface.mapCanvas().mapSettings().destinationCrs()
            ))

        for file in files:
            bn = os.path.basename(file)
            a = menuBounds.addAction(bn)
            a.setToolTip('Use spatial extent of '.format(file))
            a.triggered.connect(lambda file=file: self.setBoundsFromFile(file))
            a.setIcon(QIcon(':/vrtbuilder/mIconRaster.svg'))

            a = menuResolution.addAction(bn)
            a.setToolTip('Use resolution from'.format(file))
            a.setIcon(QIcon(':/vrtbuilder/mIconRaster.svg'))
            a.triggered.connect(lambda file=file: self.setResolutionFrom(file))

        self.btnBoundsFromFile.setMenu(menuBounds)
        self.btnResFromFile.setMenu(menuResolution)

    def onExtentChanged(self, *args):

        if not self.frameExtent.isEnabled():
            self.vrtRaster.setExtent(None)
        else:
            values = [tb.text() for tb in [self.tbBoundsXMin, self.tbBoundsYMin, self.tbBoundsXMax, self.tbBoundsYMax]]
            if '' not in values:
                values = [float(v) for v in values]
                rectangle = QgsRectangle(*values)
                if rectangle.width() > 0 and rectangle.height() > 0:
                    self.vrtRaster.setExtent(rectangle)
        self.validateInputs()

    def validateInputs(self, *args):

        isValid = len(self.vrtRaster) > 0
        if not self.cbBoundsFromSourceFiles.isEnabled():
            for tb in [self.tbBoundsXMin, self.tbBoundsXMax, self.tbBoundsYMin, self.tbBoundsYMax]:
                state, _, _ = tb.validator().validate(tb.text(), 0)
                isValid &= state == QValidator.Acceptable
            if isValid:
                isValid &= float(self.tbBoundsXMin.text()) < float(self.tbBoundsXMax.text())
                isValid &= float(self.tbBoundsYMin.text()) < float(self.tbBoundsYMax.text())

        mode = str(self.cbResolution.currentText())
        if mode == 'user':
            for tb in [self.tbResolutionX, self.tbResolutionY]:
                state, _, _ = tb.validator().validate(tb.text(), 0)
                isValid &= state == QValidator.Acceptable

        self.buttonBox.button(QDialogButtonBox.Save).setEnabled(isValid)

    def onResolutionChanged(self, *args):

        mode = self.cbResolution.currentText()
        isUserMode = mode == 'user'
        self.frameUserResolution.setEnabled(isUserMode)
        self.btnResFromFile.setEnabled(isUserMode)

        if isUserMode:
            x = self.tbResolutionX.text()
            y = self.tbResolutionY.text()
            if len(x) > 0 and len(y) > 0:
                x = float(x)
                y = float(y)
                self.vrtRaster.setResolution(QSizeF(x, y))
        else:
            self.vrtRaster.setResolution(mode)

        self.validateInputs()

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
        settings.setValue('CRS_FROM_INPUT_DATA', self.cbCRSFromInputData.isChecked())
        settings.setValue('AUTOMATIC_BOUNDS', self.cbBoundsFromSourceFiles.isChecked())

    def restoreLastSettings(self):
        from vrtbuilder.utils import settings
        settings = settings()
        assert isinstance(settings, QSettings)
        from os.path import expanduser
        self.mQgsFileWidget.setFilePath(settings.value('PATH_SAVE', os.path.join(expanduser('~'), 'output.vrt')))
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
        #reg = QgsMapLayerRegistry.instance()

        sources = set(lyr.source() for lyr in list(QgsProject.instance().mapLayers().values()) if isinstance(lyr, QgsRasterLayer))
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

    def _saveFileCallback(self, percent, x, path):
        self.progressBar.setValue(int(percent * 100))
        if x != '':
            self.tbProgress == x

    def saveFile(self):

        dsDst = None

        path = self.mQgsFileWidget.filePath()
        ext = os.path.splitext(path)[-1]

        saveBinary = ext != '.vrt'
        if saveBinary:
            pathVrt = path + '.vrt'
            self.vrtRaster.saveVRT(pathVrt)

            ext = ext.lower()
            if ext in LUT_FILEXTENSIONS.keys():
                drv = LUT_FILEXTENSIONS[ext]
            else:
                drv = gdal.GetDriverByName(str('VRT')).encode('utf-8')

            co = []
            if drv == 'ENVI':
                if ext in ['.bsq', '.bip', '.bil']:
                    co.append('INTERLEAVE={}'.format(ext[1:].upper()))

            options = gdal.TranslateOptions(format=str(drv), creationOptions=co,
                                            callback=self._saveFileCallback, callback_data=path)

            self.tbProgress.setText('Save {}...'.format(path))
            dsDst = gdal.Translate(path, pathVrt, options=options)

        else:
            pathVrt = path
            self.tbProgress.setText('Save {}...'.format(pathVrt))
            dsDst = self.vrtRaster.saveVRT(pathVrt)
            self.tbProgress.setText('{} saved'.format(pathVrt))

        if isinstance(dsDst, gdal.Dataset):
            self.tbProgress.setText('{} saved'.format(path))
        else:
            self.tbProgress.setText('Failed to save {}!'.format(path))

        dsDst = None
        if self.cbAddToMap.isChecked():
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

    def addSourceFile(self, file):

        self.addSourceFiles([file])

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
