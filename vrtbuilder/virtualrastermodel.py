# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    virtualrastermodel.py
    ---------------------
    Date                 : March 2026
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

Models for Virtual Raster Builder using QStandardItemModel
"""

import enum
import json
import os
import pathlib
import typing
from collections import OrderedDict
from typing import List

from PyQt5.QtCore import QByteArray

from qgis.PyQt.QtCore import Qt, QSortFilterProxyModel, QUrl, QMimeData, QModelIndex, pyqtSignal
from qgis.PyQt.QtGui import QIcon, QStandardItemModel, QStandardItem
from qgis.PyQt.QtWidgets import QTreeView
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import QgsRasterLayer, QgsCoordinateReferenceSystem
from vrtbuilder.qgispluginsupport.qps.utils import qgsRasterLayers
from vrtbuilder.virtualrasters import VRTRaster, VRTRasterBand, VRTInputRasterBand

# MIME types for drag and drop
MDK_BANDLIST = 'hub.vrtbuilder/bandlist'
MDK_INDICES = 'hub.vrtbuilder/vrt.indices'


class DropMode(enum.Enum):
    """Drop modes for VRT band creation"""
    NestedStack = 'NESTED_STACK'
    Stack = 'PURE_STACK'

    @staticmethod
    def toolTip(mode) -> str:
        if mode == DropMode.NestedStack:
            return 'Drop source bands with same band numbers into same virtual bands (nested by band number).'
        elif mode == DropMode.Stack:
            return 'Drop source bands with same band numbers into different virtual bands (stacked bands).'
        else:
            return ''


# Custom roles for storing data
ROLE_NODE_TYPE = Qt.UserRole + 1
ROLE_SOURCE_BAND = Qt.UserRole + 2
ROLE_VRT_BAND = Qt.UserRole + 3
ROLE_RASTER_LAYER = Qt.UserRole + 4


class NodeType(enum.Enum):
    """Types of nodes in the models"""
    ROOT = 'root'
    SOURCE_FILE = 'source_file'
    SOURCE_BAND_GROUP = 'source_band_group'
    SOURCE_BAND = 'source_band'
    VRT_ROOT = 'vrt_root'
    VRT_BAND = 'vrt_band'
    VRT_SOURCE = 'vrt_source'
    INFO = 'info'


def sourceBaseName(source) -> str:
    """Returns the base name of a source"""
    if isinstance(source, str):
        return os.path.basename(source)
    elif isinstance(source, QgsRasterLayer):
        if source.dataProvider().name() == 'gdal':
            return os.path.basename(source.source())
        else:
            return source.name()
    return str(source)


def sourceIcon(source) -> QIcon:
    """Returns an appropriate icon for the source"""
    if isinstance(source, (str, QgsRasterLayer)):
        return QIcon(r':/images/themes/default/mIconRaster.svg')
    return QIcon()


class BaseStandardItem(QStandardItem):
    """Base class for custom QStandardItem with helper methods"""

    def __init__(self, text='', node_type=None):
        super().__init__(text)
        if node_type:
            self.setData(node_type, ROLE_NODE_TYPE)

    def nodeType(self) -> NodeType:
        """Returns the node type"""
        return self.data(ROLE_NODE_TYPE)

    def findChildrenByType(self, node_type: NodeType) -> typing.List['BaseStandardItem']:
        """Find all children of a specific type"""
        result = []
        for row in range(self.rowCount()):
            child = self.child(row, 0)
            if isinstance(child, BaseStandardItem) and child.nodeType() == node_type:
                result.append(child)
        return result

    def findChildrenByTypeRecursive(self, node_type: NodeType) -> typing.List['BaseStandardItem']:
        """Find all descendants of a specific type"""
        result = []
        for row in range(self.rowCount()):
            child = self.child(row, 0)
            if isinstance(child, BaseStandardItem):
                if child.nodeType() == node_type:
                    result.append(child)
                result.extend(child.findChildrenByTypeRecursive(node_type))
        return result


class SourceRasterBandItem(BaseStandardItem):
    """Item representing a source raster band"""

    def __init__(self, vrtRasterInputSourceBand: VRTInputRasterBand):
        assert isinstance(vrtRasterInputSourceBand, VRTInputRasterBand)

        b = vrtRasterInputSourceBand.mBandIndex + 1
        super().__init__(str(b), NodeType.SOURCE_BAND)

        self.setData(vrtRasterInputSourceBand, ROLE_SOURCE_BAND)
        self.setToolTip(f'band {b}:{vrtRasterInputSourceBand.mSource}')

        # Second column with band name
        name_item = QStandardItem(vrtRasterInputSourceBand.mBandName)
        self.setChild(0, 1, name_item)

    def sourceBand(self) -> VRTInputRasterBand:
        """Returns the VRTRasterInputSourceBand"""
        return self.data(ROLE_SOURCE_BAND)

    def source(self) -> str:
        """Returns the source path"""
        band = self.sourceBand()
        return band.source() if band else ''


class SourceRasterFileItem(BaseStandardItem):
    """Item representing a source raster file"""

    def __init__(self, mapLayer: QgsRasterLayer):
        name = mapLayer.name()
        if name == '':
            name = os.path.basename(mapLayer.source())

        super().__init__(name, NodeType.SOURCE_FILE)
        assert isinstance(mapLayer, QgsRasterLayer)
        assert mapLayer.dataProvider().name() == 'gdal'

        self.setIcon(QIcon(":/vrtbuilder/mIconRaster.svg"))
        self.setData(mapLayer, ROLE_RASTER_LAYER)

        path = mapLayer.source()

        # Create info nodes
        src_item = BaseStandardItem('Path', NodeType.INFO)
        src_value = QStandardItem(path)
        self.appendRow([src_item, src_value])

        crs: QgsCoordinateReferenceSystem = mapLayer.crs()
        crs_item = BaseStandardItem('CRS', NodeType.INFO)
        authInfo = f'{crs.description()} {crs.authid()}'
        crs_value = QStandardItem(authInfo)
        crs_value.setToolTip(crs.toWkt())
        self.appendRow([crs_item, crs_value])

        # Create bands group
        bands_item = BaseStandardItem('Bands', NodeType.SOURCE_BAND_GROUP)
        for b in range(mapLayer.bandCount()):
            bandName = mapLayer.bandName(b + 1)
            inputSource = VRTInputRasterBand(path, b, bandName=bandName)
            inputSource.mBandName = bandName
            inputSource.mNoData = mapLayer.dataProvider().sourceNoDataValue(b + 1)
            band_item = SourceRasterBandItem(inputSource)
            bands_item.appendRow(band_item)

        self.appendRow(bands_item)

    def source(self) -> str:
        """Returns the source path"""
        layer = self.rasterLayer()
        return layer.source() if layer else ''

    def sourceBands(self) -> typing.List[VRTInputRasterBand]:
        """Returns all source bands"""
        bands_items = self.findChildrenByType(NodeType.SOURCE_BAND_GROUP)
        if not bands_items:
            return []

        result = []
        for row in range(bands_items[0].rowCount()):
            band_item = bands_items[0].child(row, 0)
            if isinstance(band_item, SourceRasterBandItem):
                result.append(band_item.sourceBand())
        return result

    def rasterLayer(self) -> QgsRasterLayer:
        """Returns the QgsRasterLayer"""
        return self.data(ROLE_RASTER_LAYER)


class SourceRasterModel(QStandardItemModel):
    """Model for source raster files"""

    sigSourcesAdded = pyqtSignal()
    sigSourcesRemoved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(['File/Band', 'Value/Description'])

    def __len__(self):
        return len(self.rasterSources())

    def __iter__(self):
        return iter(self.rasterSources())

    def __contains__(self, file):
        return pathlib.Path(file).resolve().as_posix() in self.rasterSources()

    def rasterSources(self) -> List[str]:
        """Returns list of raster source paths"""
        return [pathlib.Path(l.source()).as_posix() for l in self.rasterLayers()]

    def rasterLayers(self) -> list:
        """Returns the list of QgsRasterLayers"""
        result = []
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if isinstance(item, SourceRasterFileItem):
                result.append(item.rasterLayer())
        return result

    def addSource(self, rasterSource):
        """Add a single source"""
        self.addSources([rasterSource])

    def addSources(self, rasterSources):
        """Add multiple sources"""
        assert isinstance(rasterSources, list)
        existingSources = self.rasterSources()

        newLayers = qgsRasterLayers(rasterSources)
        newLayers = [l for l in newLayers if isinstance(l, QgsRasterLayer) and
                     pathlib.Path(l.source()).as_posix() not in existingSources]

        if len(newLayers) > 0:
            for lyr in newLayers:
                item = SourceRasterFileItem(lyr)
                self.appendRow(item)
            self.sigSourcesAdded.emit()

    def file2item(self, file: str) -> SourceRasterFileItem:
        """Get item for a file path"""
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if isinstance(item, SourceRasterFileItem) and item.source() == file:
                return item
        return None

    def file2layer(self, file: str) -> QgsRasterLayer:
        """Get layer for a file path"""
        item = self.file2item(file)
        return item.rasterLayer() if item else None

    def removeFiles(self, listOfFiles):
        """Remove files from the model"""
        assert isinstance(listOfFiles, list)

        rows_to_remove = []
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if isinstance(item, SourceRasterFileItem) and item.source() in listOfFiles:
                rows_to_remove.append(row)

        # Remove in reverse order to maintain indices
        for row in sorted(rows_to_remove, reverse=True):
            self.removeRow(row)

        if rows_to_remove:
            self.sigSourcesRemoved.emit()

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsDropEnabled

        flags = super().flags(index)
        item = self.itemFromIndex(index)

        flags |= Qt.ItemIsSelectable
        if isinstance(item, (SourceRasterFileItem, SourceRasterBandItem)):
            flags |= Qt.ItemIsDragEnabled

        return flags

    def dropMimeData(self, mimeData, action, row, col, parentIndex):
        """Handle dropped data"""
        assert isinstance(mimeData, QMimeData)

        if mimeData.hasUrls():
            self.addSources(mimeData.urls())
            return True

        elif 'application/qgis.layertreemodeldata' in mimeData.formats():
            doc = QDomDocument()
            doc.setContent(mimeData.data('application/qgis.layertreemodeldata'))
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
        """Supported MIME types"""
        return ['text/uri-list', 'application/qgis.layertreemodeldata',
                'application/x-vnd.qgis.qgis.uri', MDK_BANDLIST]

    def mimeData(self, indexes):
        """Create MIME data for dragging"""
        if not indexes:
            return None

        # Get unique items (only from first column)
        items = []
        for idx in indexes:
            if idx.column() == 0:
                item = self.itemFromIndex(idx)
                if item not in items:
                    items.append(item)

        sourceBands = []
        for item in items:
            if isinstance(item, SourceRasterFileItem):
                sourceBands.extend(item.sourceBands())
            elif isinstance(item, SourceRasterBandItem):
                sourceBands.append(item.sourceBand())

        sourceBands = list(OrderedDict.fromkeys(sourceBands))
        uriList = [sourceBand.mSource for sourceBand in sourceBands]
        uriList = list(OrderedDict.fromkeys(uriList))

        mimeData = QMimeData()

        if len(sourceBands) > 0:
            source_band_data = [band.toMap() for band in sourceBands]
            dump = QByteArray(json.dumps(source_band_data, ensure_ascii=False).encode('utf-8'))
            mimeData.setData(MDK_BANDLIST, dump)

        if len(uriList) > 0:
            mimeData.setUrls([QUrl(p) for p in uriList])

        return mimeData


class SourceRasterFilterModel(QSortFilterProxyModel):
    """Filter model for source rasters"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRecursiveFilteringEnabled(True)
        self.setSortRole(Qt.EditRole)
        self.setDynamicSortFilter(True)
        self.rowsInserted.connect(self.initSorting)

    def initSorting(self, idx, first, last):
        """Initialize sorting on first insertion"""
        self.sort(0, Qt.AscendingOrder)
        self.rowsInserted.disconnect(self.initSorting)

    def lessThan(self, idx1: QModelIndex, idx2: QModelIndex) -> bool:
        """Custom sorting logic"""
        item1 = self.sourceModel().itemFromIndex(idx1)
        item2 = self.sourceModel().itemFromIndex(idx2)

        if isinstance(item1, SourceRasterBandItem) and isinstance(item2, SourceRasterBandItem):
            return item1.sourceBand().bandIndex() < item2.sourceBand().bandIndex()

        # Keep Bands group nodes in place
        if isinstance(item1, BaseStandardItem) and isinstance(item2, BaseStandardItem):
            if item1.nodeType() == NodeType.SOURCE_BAND_GROUP:
                return False
            if item2.nodeType() == NodeType.SOURCE_BAND_GROUP:
                return True

        return super().lessThan(idx1, idx2)

    def filterAcceptsRow(self, sourceRow, sourceParent):
        """Filter logic"""
        reg = self.filterRegExp()
        if reg.isEmpty():
            return True

        source_model = self.sourceModel()
        index = source_model.index(sourceRow, 0, sourceParent)
        item = source_model.itemFromIndex(index)

        if not isinstance(item, BaseStandardItem):
            return False

        # Always show info nodes if parent is shown
        if item.nodeType() in [NodeType.INFO, NodeType.SOURCE_BAND_GROUP]:
            return True

        # Filter files and bands
        if isinstance(item, (SourceRasterFileItem, SourceRasterBandItem)):
            text = item.text()
            if reg.indexIn(text) >= 0:
                return True
            # Also check second column
            if item.columnCount() > 1:
                col2_item = self.sourceModel().item(item.row(), 1)
                if col2_item and reg.indexIn(col2_item.text()) >= 0:
                    return True

        return False


class SourceRasterTreeView(QTreeView):
    """Tree view for source rasters"""

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)


# ============================================================================
# VRT Raster Model Classes
# ============================================================================


class VRTRasterInputSourceBandItem(BaseStandardItem):
    """Item representing an input source band in a VRT"""

    def __init__(self, vrtRasterInputSourceBand: VRTInputRasterBand):
        assert isinstance(vrtRasterInputSourceBand, VRTInputRasterBand)

        path = vrtRasterInputSourceBand.source()
        bn = os.path.basename(path)
        b = vrtRasterInputSourceBand.bandIndex() + 1

        super().__init__(f'{bn}:{b}', NodeType.VRT_SOURCE)
        self.setIcon(QIcon(":/vrtbuilder/mIconRaster.svg"))
        self.setData(vrtRasterInputSourceBand, ROLE_SOURCE_BAND)
        self.setToolTip(f'Band {b} from "{path}"')

        # Second column with full path
        path_item = QStandardItem(f'{path}:{b}')
        self.setChild(0, 1, path_item)

    def sourceBand(self) -> VRTInputRasterBand:
        """Returns the VRTRasterInputSourceBand"""
        return self.data(ROLE_SOURCE_BAND)

    def source(self) -> str:
        """Returns the source path"""
        band = self.sourceBand()
        return band.source() if band else ''


class VRTRasterBandItem(BaseStandardItem):
    """Item representing a VRT band"""

    def __init__(self, virtualBand: VRTRasterBand):
        assert isinstance(virtualBand, VRTRasterBand)

        super().__init__(virtualBand.name(), NodeType.VRT_BAND)
        self.setIcon(QIcon(":/vrtbuilder/mIconVirtualRaster.svg"))
        self.setData(virtualBand, ROLE_VRT_BAND)

        # Connect signals
        virtualBand.sigNameChanged.connect(self.onNameChanged)
        virtualBand.sigSourceInserted.connect(self.onSourceInserted)
        virtualBand.sigSourceRemoved.connect(self.onSourceRemoved)

        # Add existing sources
        for src in virtualBand:
            self.addSourceItem(src, virtualBand.mSources.index(src))

    def onNameChanged(self, name: str):
        """Handle name changes"""
        self.setText(name)

    def onSourceInserted(self, index: int, inputSource: VRTInputRasterBand):
        """Handle source insertion"""
        self.addSourceItem(inputSource, index)

    def onSourceRemoved(self, row: int, inputSource: VRTInputRasterBand):
        """Handle source removal"""
        # Find and remove the item
        for i in range(self.rowCount()):
            child = self.child(i, 0)
            if isinstance(child, VRTRasterInputSourceBandItem):
                if child.sourceBand() == inputSource:
                    self.removeRow(i)
                    break

    def addSourceItem(self, inputSource: VRTInputRasterBand, index: int):
        """Add a source item at the specified index"""
        item = VRTRasterInputSourceBandItem(inputSource)
        self.insertRow(index, item)

    def virtualBand(self) -> VRTRasterBand:
        """Returns the VRTRasterBand"""
        return self.data(ROLE_VRT_BAND)


class VRTRasterRootItem(BaseStandardItem):
    """Root item for VRT raster"""

    def __init__(self, vrtRaster: VRTRaster):
        assert isinstance(vrtRaster, VRTRaster)

        super().__init__('VRT Bands', NodeType.VRT_ROOT)
        self.setData(vrtRaster, Qt.UserRole)

        # Connect signals
        vrtRaster.sigVirtualBandInserted.connect(self.onBandInserted)
        vrtRaster.sigVirtualBandRemoved.connect(self.onBandRemoved)

    def onBandInserted(self, index: int, vrtRasterBand: VRTRasterBand):
        """Handle band insertion"""
        item = VRTRasterBandItem(vrtRasterBand)
        self.insertRow(index, item)

    def onBandRemoved(self, index: int, vrtRasterBand: VRTRasterBand):
        """Handle band removal"""
        self.removeRow(index)

    def vrtRaster(self) -> VRTRaster:
        """Returns the VRTRaster"""
        return self.data(Qt.UserRole)


class VRTRasterTreeModel(QStandardItemModel):
    """Model for VRT raster structure"""

    def __init__(self, vrtRaster: VRTRaster, parent=None):
        assert isinstance(vrtRaster, VRTRaster)

        super().__init__(parent)
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(['Virtual/Source Band', 'Source Path'])

        self.mVRTRaster = vrtRaster
        self.mDropMode: DropMode = DropMode.NestedStack

        # Create root item
        root_item = VRTRasterRootItem(vrtRaster)
        self.appendRow(root_item)

        # Add existing bands
        for band in vrtRaster:
            root_item.onBandInserted(vrtRaster.mBands.index(band), band)

    def setDropMode(self, mode: DropMode):
        """Set the drop mode"""
        assert isinstance(mode, DropMode)
        self.mDropMode = mode

    def rootVRTItem(self) -> VRTRasterRootItem:
        """Get the root VRT item"""
        item = self.item(0, 0)
        if isinstance(item, VRTRasterRootItem):
            return item
        return None

    def setData(self, index, value, role=Qt.EditRole):
        """Handle data changes"""
        if role == Qt.EditRole and index.column() == 0:
            item = self.itemFromIndex(index)
            if isinstance(item, VRTRasterBandItem):
                if len(value) > 0:
                    item.setText(value)
                    item.virtualBand().setName(value)
                    return True

        return super().setData(index, value, role)

    def removeNodes(self, items):
        """Remove items from the model"""
        for item in items:
            if isinstance(item, VRTRasterBandItem):
                self.mVRTRaster.removeVirtualBand(item.virtualBand())

            elif isinstance(item, VRTRasterInputSourceBandItem):
                srcBand = item.sourceBand()
                parent = item.parent()
                if isinstance(parent, VRTRasterBandItem):
                    parent.virtualBand().removeSource(srcBand)

    def flags(self, index):
        """Return item flags"""
        if not index.isValid():
            return Qt.ItemIsDropEnabled

        item = self.itemFromIndex(index)
        flags = super().flags(index)

        if isinstance(item, VRTRasterBandItem):
            flags |= Qt.ItemIsDropEnabled
            flags |= Qt.ItemIsEditable

        if isinstance(item, VRTRasterInputSourceBandItem):
            flags |= Qt.ItemIsDropEnabled
            flags |= Qt.ItemIsDragEnabled

        return flags

    def mimeTypes(self):
        """Supported MIME types"""
        return ['text/uri-list', MDK_BANDLIST]

    def mimeData(self, indexes):
        """Create MIME data for dragging"""
        if not indexes:
            return None

        # Get unique items (only from first column)
        items = []
        for idx in indexes:
            if idx.column() == 0:
                item = self.itemFromIndex(idx)
                if item not in items:
                    items.append(item)

        sourceBands = []
        for item in items:
            if isinstance(item, VRTRasterInputSourceBandItem):
                sourceBand = item.sourceBand()
                if sourceBand:
                    sourceBands.append(sourceBand)

        sourceBands = list(OrderedDict.fromkeys(sourceBands))
        uriList = [sourceBand.mSource for sourceBand in sourceBands]
        uriList = list(OrderedDict.fromkeys(uriList))

        mimeData = QMimeData()

        if len(sourceBands) > 0:
            source_band_data = [band.toMap() for band in sourceBands]
            dump = QByteArray(json.dumps(source_band_data, ensure_ascii=False).encode('utf-8'))
            mimeData.setData(MDK_BANDLIST, dump)

        if len(uriList) > 0:
            mimeData.setUrls([QUrl(p) for p in uriList])
            mimeData.setText('\n'.join(uriList))

        return mimeData

    def dropMimeData(self, mimeData, action, row, col, parentIndex):
        """Handle dropped data"""
        import re

        if action == Qt.IgnoreAction:
            return True

        assert isinstance(mimeData, QMimeData)
        sourceBands = []

        # Parse MIME data
        if MDK_BANDLIST in mimeData.formats():
            dump = mimeData.data(MDK_BANDLIST)
            json_string = bytes(dump).decode('utf-8')
            sourceBands = [VRTInputRasterBand.fromMap(d) for d in json.loads(json_string)]

        elif mimeData.hasUrls():
            for url in mimeData.urls():
                path = url.toLocalFile() if url.isLocalFile() else url.toString()
                if path:
                    sourceBands.extend(VRTInputRasterBand.fromRasterLayer(path))

        if not sourceBands:
            return False

        # Process drop mode
        if self.mDropMode == DropMode.NestedStack:
            # Group by source image
            sourceImages = {}
            for b in sourceBands:
                if b.mSource not in sourceImages:
                    sourceImages[b.mSource] = []
                sourceImages[b.mSource].append(b)

            for p in sourceImages.keys():
                sourceImages[p] = sorted(sourceImages[p], key=lambda b: b.mBandIndex)

            if not sourceImages:
                return True

            # Create nested list
            sourceBands = []
            while sourceImages:
                sourceBands.append([])
                for k in list(sourceImages.keys()):
                    sourceBands[-1].append(sourceImages[k].pop(0))
                    if not sourceImages[k]:
                        del sourceImages[k]

        elif self.mDropMode == DropMode.Stack:
            sourceBands = [[b] for b in sourceBands]
        else:
            raise NotImplementedError(f'Unknown DropMode: "{self.mDropMode}"')

        # Find target band
        parentItem = self.itemFromIndex(parentIndex)

        # Navigate to VRTRasterBandItem
        if isinstance(parentItem, VRTRasterInputSourceBandItem):
            parentItem = parentItem.parent()

        elif isinstance(parentItem, VRTRasterRootItem):
            # Create new band if needed
            vBand = VRTRasterBand()
            self.mVRTRaster.addVirtualBand(vBand)
            # Get the newly created item
            parentItem = parentItem.child(parentItem.rowCount() - 1, 0)

        if not isinstance(parentItem, VRTRasterBandItem):
            return False

        vBand = parentItem.virtualBand()
        if row < 0:
            row = 0

        # Add source bands
        for bands in sourceBands:
            iSrc = row
            for src in bands:
                if len(vBand) == 0 and re.search(r'Band \d+$', vBand.name(), re.I):
                    vBand.setName(src.name())
                vBand.insertSource(iSrc, src)
                iSrc += 1

            if bands != sourceBands[-1]:
                # Add new virtual band if needed
                if vBand == self.mVRTRaster.mBands[-1]:
                    self.mVRTRaster.addVirtualBand(VRTRasterBand())

                # Go to next virtual band
                vBand = self.mVRTRaster.mBands[self.mVRTRaster.mBands.index(vBand) + 1]

        return True

    def supportedDragActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction


class VRTRasterTreeView(QTreeView):
    """Tree view for VRT raster"""

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setEditTriggers(QTreeView.DoubleClicked | QTreeView.EditKeyPressed)
