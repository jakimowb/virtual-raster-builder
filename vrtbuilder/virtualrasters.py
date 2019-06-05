# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
/***************************************************************************
                              Virtual Raster Builder
                              ----------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 3 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import os, sys, re, pickle, tempfile, uuid, warnings, pathlib
from xml.etree import ElementTree
from collections import OrderedDict
import tempfile
from osgeo import gdal, osr, ogr, gdalconst as gc
from qgis.core import *
from qgis.gui import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from vrtbuilder import toRasterLayer, toDataset
from vrtbuilder.models import Option, OptionListModel
#lookup GDAL Data Type and its size in bytes
LUT_GDT_SIZE = {gdal.GDT_Byte:1,
                gdal.GDT_UInt16:2,
                gdal.GDT_Int16:2,
                gdal.GDT_UInt32:4,
                gdal.GDT_Int32:4,
                gdal.GDT_Float32:4,
                gdal.GDT_Float64:8,
                gdal.GDT_CInt16:2,
                gdal.GDT_CInt32:4,
                gdal.GDT_CFloat32:4,
                gdal.GDT_CFloat64:8}

LUT_GDT_NAME = {gdal.GDT_Byte:'Byte',
                gdal.GDT_UInt16:'UInt16',
                gdal.GDT_Int16:'Int16',
                gdal.GDT_UInt32:'UInt32',
                gdal.GDT_Int32:'Int32',
                gdal.GDT_Float32:'Float32',
                gdal.GDT_Float64:'Float64',
                gdal.GDT_CInt16:'Int16',
                gdal.GDT_CInt32:'Int32',
                gdal.GDT_CFloat32:'Float32',
                gdal.GDT_CFloat64:'Float64'}


GRA_tooltips = {'NearestNeighbour':'nearest neighbour resampling (default, fastest algorithm, worst interpolation quality).',
              'Bilinear':'bilinear resampling.',
              'Lanczos':'lanczos windowed sinc resampling.',
              'Average':'average resampling, computes the average of all non-NODATA contributing pixels.',
              'Cubic':'cubic resampling.',
              'CubicSpline':'cubic spline resampling.',
              'Mode':'mode resampling, selects the value which appears most often of all the sampled points',
              'Max':'maximum resampling, selects the maximum value from all non-NODATA contributing pixels',
              'Min':'minimum resampling, selects the minimum value from all non-NODATA contributing pixels.',
              'Med':'median resampling, selects the median value of all non-NODATA contributing pixels.',
              'Q1':'first quartile resampling, selects the first quartile value of all non-NODATA contributing pixels. ',
              'Q3':'third quartile resampling, selects the third quartile value of all non-NODATA contributing pixels'
              }




def vsiFiles()->list:
    """
    Returns the URIs pointing on VSIMEM files
    :return: [list-of-str]
    """
    files = gdal.ReadDirRecursive('/vsimem/')
    if isinstance(files, list):
        return ['/vsimem/' + p for p in files if not p.endswith('/')]
    return []


#get available resampling algorithms
RESAMPLE_ALGS = OptionListModel()
for GRAkey in [k for k in list(gdal.__dict__.keys()) if k.startswith('GRA_')]:

    GRA = gdal.__dict__[GRAkey]
    GRA_Name = GRAkey[4:]

    option = Option(GRA, GRA_Name, tooltip=GRA_tooltips.get(GRA_Name))
    RESAMPLE_ALGS.addOption(option)


# thanks to https://gis.stackexchange.com/questions/75533/how-to-apply-band-settings-using-gdal-python-bindings
def read_vsimem(fn):
    """
    Reads VSIMEM path as string
    :param fn: vsimem path (str)
    :return: result of gdal.VSIFReadL(1, vsileng, vsifile)
    """
    vsifile = gdal.VSIFOpenL(fn,'r')
    gdal.VSIFSeekL(vsifile, 0, 2)
    vsileng = gdal.VSIFTellL(vsifile)
    gdal.VSIFSeekL(vsifile, 0, 0)
    return gdal.VSIFReadL(1, vsileng, vsifile)

def write_vsimem(fn:str,data:str):
    """
    Writes data to vsimem path
    :param fn: vsimem path (str)
    :param data: string to write
    :return: result of gdal.VSIFCloseL(vsifile)
    """
    '''Write GDAL vsimem files'''
    vsifile = gdal.VSIFOpenL(fn,'w')
    size = len(data)
    gdal.VSIFWriteL(data, 1, size, vsifile)
    return gdal.VSIFCloseL(vsifile)


def resolution(lyr)->QSizeF:
    """Returns the pixel resolution of a QgsRasterLayer or gdal.Dataset"""
    if isinstance(lyr, QgsRasterLayer):
        return QSizeF(lyr.rasterUnitsPerPixelX(), lyr.rasterUnitsPerPixelY())
    elif isinstance(lyr, gdal.Dataset):
        gt = lyr.GetGeoTransform()
        return QSizeF(gt[1], abs(gt[5]))
    else:
        raise Exception('Unsupported type: {}'.format(lyr))


def px2geo(px, gt)->QgsPointXY:
    """
    :param px:
    :param gt:
    :return:
    """
    gx = gt[0] + px.x()*gt[1]+px.y()*gt[2]
    gy = gt[3] + px.x()*gt[4]+px.y()*gt[5]
    return QgsPointXY(gx, gy)


def geo2pxF(geo, gt):
    """
    Returns the pixel position related to a Geo-Coordinate in floating point precision.
    :param geo: Geo-Coordinate as QgsPoint
    :param gt: GDAL Geo-Transformation tuple, as described in http://www.gdal.org/gdal_datamodel.html
    :return: pixel position as QPointF
    """
    assert isinstance(geo, QgsPointXY)
    # see http://www.gdal.org/gdal_datamodel.html
    px = (geo.x() - gt[0]) / gt[1]  # x pixel
    py = (geo.y() - gt[3]) / gt[5]  # y pixel
    return QPointF(px, py)


def geo2px(geo, gt):
    """
    Returns the pixel position related to a Geo-Coordinate as integer number.
    Floating-point coordinate are casted to integer coordinate, e.g. the pixel coordinate (0.815, 23.42) is returned as (0,23)
    :param geo: Geo-Coordinate as QgsPointXY
    :param gt: GDAL Geo-Transformation tuple, as described in http://www.gdal.org/gdal_datamodel.html or
          gdal.Dataset or QgsRasterLayer
    :return: pixel position as QPpint
    """

    if isinstance(gt, QgsRasterLayer):
        return geo2px(geo, geotransform(gt))
    elif isinstance(gt, gdal.Dataset):
        return geo2px(gt.GetGeoTransform())
    else:
        px = geo2pxF(geo, gt)
        return QPoint(int(px.x()), int(px.y()))


def transformBoundingBox(rectangle:QgsRectangle, trans:QgsCoordinateTransform)->QgsRectangle:
    """
    Transforms a minimum bounding box into another CRS.
    :param rectangle: QgsRectangle
    :param trans: QgsCoordinateTransform
    :return: QgsRectangle
    """
    assert isinstance(rectangle, QgsRectangle)
    assert isinstance(trans, QgsCoordinateTransform)

    pts = [QgsPointXY(rectangle.xMinimum(), rectangle.yMinimum()),
           QgsPointXY(rectangle.xMinimum(), rectangle.yMaximum()),
           QgsPointXY(rectangle.xMaximum(), rectangle.yMinimum()),
           QgsPointXY(rectangle.xMaximum(), rectangle.yMaximum())
           ]
    pts = [trans.transform(pt) for pt in pts]

    xvalues = [pt.x() for pt in pts]
    yvalues = [pt.y() for pt in pts]

    xMin = min(xvalues)
    xMax = max(xvalues)
    yMin = min(yvalues)
    yMax = max(yvalues)

    return QgsRectangle(xMin, yMin, xMax, yMax)


def geotransform(upperLeft:QgsPointXY, resolution:QSizeF)->tuple:
    """
    Create a GeoTransformation tuple
    :param upperLeft: QgsPointXY upper left image coordinate
    :param resolution: QSizeF, pixel resolution
    :return: tuple
    """
    if isinstance(upperLeft, QgsRasterLayer):
        resolution = resolution(upperLeft)
        upperLeft = QgsPointXY(upperLeft.extent().xMinimum(), upperLeft.extent().yMaximum())
    if isinstance(upperLeft, gdal.Dataset):
        return upperLeft.GetGeoTransform()
    if isinstance(upperLeft, gdal.Band):
        return upperLeft.GetDataset().GetGeoTransform()

    assert resolution.height() > 0
    assert resolution.width() > 0
    gt = (upperLeft.x(), resolution.width(), 0,
          upperLeft.y(), 0, resolution.height())
    return gt

def alignPointToGrid(pixelSize:QSizeF, gridRefPoint:QgsPointXY, gridPoint:QgsPointXY)->QgsPointXY:
    """
    Shift a point onto a grid defined by a pixelSize and a gridRefPoint
    :param pixelSize: QSizeF pixel size
    :param gridRefPoint: QgsPointXY point on reference grid
    :param gridPoint: QgsPointXY to alignt to reference grid
    :return: QgsPointXY
    """
    w = pixelSize.width()
    h = pixelSize.height()

    x = gridRefPoint.x() + w * int(round((gridPoint.x() - gridRefPoint.x()) / w))
    y = gridRefPoint.y() + h * int(round((gridPoint.y() - gridRefPoint.y()) / h))
    return QgsPointXY(x,y)

def alignRectangleToGrid(pixelSize: QSizeF, gridRefPoint: QgsPointXY, rectangle: QgsRectangle)->QgsRectangle:
    """
    Returns an (extent, size) aligned to the pixelSize and reference grid
    :param pixelSize: QSizeF, pixel size
    :param gridRefPoint: QgsPointXY, a reference grid location, i.e. a pixel corner
    :param rectangle: QgsRectangle. the extent to get aligned
    :return: tuple (QgsRectangle, QSize)
    """

    w = pixelSize.width()
    h = pixelSize.height()

    xMin = gridRefPoint.x() + w * int(round((rectangle.xMinimum() - gridRefPoint.x()) / w))
    yMax = gridRefPoint.y() + h * int(round((rectangle.yMaximum() - gridRefPoint.y()) / h))
    xMax = gridRefPoint.x() + w * int(round((rectangle.xMaximum() - gridRefPoint.x()) / w))
    yMin = gridRefPoint.y() + h * int(round((rectangle.yMinimum() - gridRefPoint.y()) / h))

    width = float(xMax - xMin)
    height = float(yMax - yMin)

    ns = int(round(width / w))
    nl = int(round(height / h))

    ns = max(1, ns)
    nl = max(1, nl)

    newExtent = QgsRectangle(xMin, yMax, xMin + ns * w, yMax - nl * h)
    size = QSize(ns, nl)
    if size.width() < 0 or size.height() < 0:
        s = ""
    return newExtent, size


def describeRawFile(pathRaw, pathVrt, xsize, ysize,
                    bands=1,
                    eType = gdal.GDT_Byte,
                    interleave='bsq',
                    byteOrder='LSB',
                    headerOffset=0):
    """
    Creates a VRT to describe a raw binary file
    :param pathRaw: path of raw image
    :param pathVrt: path of destination VRT
    :param xsize: number of image samples / columns
    :param ysize: number of image lines
    :param bands: number of image bands
    :param eType: the GDAL data type
    :param interleave: can be 'bsq' (default),'bil' or 'bip'
    :param byteOrder: 'LSB' (default) or 'MSB'
    :param headerOffset: header offset in bytes, default = 0
    :return: gdal.Dataset of created VRT
    """
    assert xsize > 0
    assert ysize > 0
    assert bands > 0
    assert eType > 0

    assert eType in LUT_GDT_SIZE.keys(), 'dataType "{}" is not a valid gdal datatype'.format(eType)
    interleave = interleave.lower()

    assert interleave in ['bsq','bil','bip']
    assert byteOrder in ['LSB', 'MSB']

    drvVRT = gdal.GetDriverByName('VRT')
    assert isinstance(drvVRT, gdal.Driver)
    dsVRT = drvVRT.Create(pathVrt, xsize, ysize, bands=0, eType=eType)
    assert isinstance(dsVRT, gdal.Dataset)

    #vrt = ['<VRTDataset rasterXSize="{xsize}" rasterYSize="{ysize}">'.format(xsize=xsize,ysize=ysize)]

    vrtDir = os.path.dirname(pathVrt)
    if pathRaw.startswith(vrtDir):
        relativeToVRT = 1
        srcFilename = os.path.relpath(pathRaw, vrtDir)
    else:
        relativeToVRT = 0
        srcFilename = pathRaw

    for b in range(bands):
        if interleave == 'bsq':
            imageOffset = headerOffset
            pixelOffset = LUT_GDT_SIZE[eType]
            lineOffset = pixelOffset * xsize
        elif interleave == 'bip':
            imageOffset = headerOffset + b * LUT_GDT_SIZE[eType]
            pixelOffset = bands * LUT_GDT_SIZE[eType]
            lineOffset = xsize * bands
        else:
            raise Exception('Interleave {} is not supported'.format(interleave))

        options = ['subClass=VRTRawRasterBand']
        options.append('SourceFilename={}'.format(srcFilename))
        options.append('dataType={}'.format(LUT_GDT_NAME[eType]))
        options.append('ImageOffset={}'.format(imageOffset))
        options.append('PixelOffset={}'.format(pixelOffset))
        options.append('LineOffset={}'.format(lineOffset))
        options.append('ByteOrder={}'.format(byteOrder))

        xml = """<SourceFilename relativetoVRT="{relativeToVRT}">{srcFilename}</SourceFilename>
            <ImageOffset>{imageOffset}</ImageOffset>
            <PixelOffset>{pixelOffset}</PixelOffset>
            <LineOffset>{lineOffset}</LineOffset>
            <ByteOrder>{byteOrder}</ByteOrder>""".format(relativeToVRT=relativeToVRT,
                                                         srcFilename=srcFilename,
                                                         imageOffset=imageOffset,
                                                         pixelOffset=pixelOffset,
                                                         lineOffset=lineOffset,
                                                         byteOrder=byteOrder)

        #md = {}
        #md['source_0'] = xml
        #vrtBand = dsVRT.GetRasterBand(b + 1)
        assert dsVRT.AddBand(eType, options=options) == 0

        vrtBand = dsVRT.GetRasterBand(b+1)
        assert isinstance(vrtBand, gdal.Band)
        #vrtBand.SetMetadata(md, 'vrt_sources')
        #vrt.append('  <VRTRasterBand dataType="{dataType}" band="{band}" subClass="VRTRawRasterBand">'.format(dataType=LUT_GDT_NAME[eType], band=b+1))
    dsVRT.FlushCache()
    return dsVRT


class VRTRasterInputSourceBand(object):

    @staticmethod
    def fromGDALDataSet(pathOrDataSet):
        """
        Returns the VRTRasterInputSourceBands from a raster data source
        :param pathOrDataSet: str | gdal.Dataset
        :return: [list-of-VRTRasterInputSourceBand]
        """

        srcBands = []

        if isinstance(pathOrDataSet, str):
            pathOrDataSet = gdal.Open(pathOrDataSet)

        if isinstance(pathOrDataSet, gdal.Dataset):
            path = pathOrDataSet.GetFileList()[0]
            for b in range(pathOrDataSet.RasterCount):
                srcBands.append(VRTRasterInputSourceBand(path, b))
        return srcBands

    @staticmethod
    def fromRasterLayer(layer:QgsRasterLayer):

        if isinstance(layer, str):
            lyr = QgsRasterLayer(layer, '', 'gdal')
            return VRTRasterInputSourceBand.fromRasterLayer(lyr)



        if not (isinstance(layer, QgsRasterLayer) and
                layer.dataProvider().name() == 'gdal' and
                layer.isValid()):
            return []

        srcBands = []
        src = layer.source()
        for b in range(layer.bandCount()):
            name = layer.bandName(b+1)
            srcBands.append(VRTRasterInputSourceBand(src, b, bandName=name))

        return srcBands


    def __init__(self, path:str, bandIndex:int, bandName:str=''):
        self.mSource = path
        self.mBandIndex = bandIndex
        self.mBandName = bandName
        self.mNoData = None
        self.mVirtualBand = None

    def name(self)->str:
        """
        Returns the band name
        :return: str
        """
        return self.mBandName

    def bandIndex(self)->int:
        """
        Returns the band index
        :return: int
        """
        return self.mBandIndex

    def source(self)->str:
        """
        Returns the source uri
        :return: str
        """
        return self.mSource

    def isEqual(self, other)->bool:
        """
        Returns True for same input sources
        :param other: VRTRasterInputSourceBand
        :return: bool
        """
        if isinstance(other, VRTRasterInputSourceBand):
            return self.mSource == other.mSource and self.mBandIndex == other.mBandIndex
        else:
            return False

    def __reduce_ex__(self, protocol):

        return self.__class__, (self.mSource, self.mBandIndex, self.mBandName), self.__getstate__()

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop('mVirtualBand')
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def virtualBand(self):
        return self.mVirtualBand

    def toDataset(self)->gdal.Dataset:
        """
        Opens the source as GDAL Dataset
        :return: gdal.Dataset
        """
        ds = gdal.Open(self.source())
        assert isinstance(ds, gdal.Dataset)
        return ds

    def toRasterLayer(self)->QgsRasterLayer:
        """
        Opens the source as QgsRasterLayer
        :return: QgsRasterLayer
        """
        lyr = QgsRasterLayer(self.source(), self.name(), 'gdal')
        #todo: set render to this specific band
        
        return lyr


class VRTRasterBand(QObject):
    sigNameChanged = pyqtSignal(str)
    sigSourceInserted = pyqtSignal(int, VRTRasterInputSourceBand)
    sigSourceRemoved = pyqtSignal(int, VRTRasterInputSourceBand)

    def __init__(self, name:str='', parent=None):
        super(VRTRasterBand, self).__init__(parent)
        self.mSources = []
        self.mName = ''
        self.setName(name)
        self.mVRT = None
        self.mMetadataDomains = dict()
        self.mClassificationScheme = None

    def __iter__(self):
        return iter(self.mSources)

    def __getitem__(self, slice):
        return self.mSources[slice]

    def __len__(self):
        return len(self.mSources)

    def setMetadata(self, metadataDictionary:dict, domain:str=""):
        assert isinstance(metadataDictionary, dict)
        self.mMetadataDomains[domain] = metadataDictionary

    def metadata(self, domain):
        if domain is None:
            domain = ""
        assert isinstance(domain, "")

    def setName(self, name:str):
        """
        Sets the band name
        :param name: str
        """
        assert isinstance(name, str)
        oldName = self.mName
        self.mName = name
        if oldName != self.mName:
            self.sigNameChanged.emit(name)

    def name(self):
        """
        Returns the band name
        :return: str
        """
        return self.mName

    def addSource(self, vrtRasterInputSourceBand:VRTRasterInputSourceBand):
        """
        Adds an input source to the virtual band
        :param vrtRasterInputSourceBand: input source
        """
        assert isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand)
        self.insertSource(len(self.mSources), vrtRasterInputSourceBand)

    def insertSource(self, index, vrtRasterInputSourceBand:VRTRasterInputSourceBand):
        """
        Inserts an input source to the list of virtual band sources
        :param index: index of input sources
        :param vrtRasterInputSourceBand: input source
        """
        assert isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand)
        vrtRasterInputSourceBand.mVirtualBand = self
        if index <= len(self.mSources):
            self.mSources.insert(index, vrtRasterInputSourceBand)
            self.sigSourceInserted.emit(index, vrtRasterInputSourceBand)
        else:
            pass
            #print('DEBUG: index <= len(self.sources)')

    def bandIndex(self)->int:
        """
        Returns the index of this Virtual Band.
        Only available if this VRTRasterBand was added to a parent VRTRaster.
        :return: int
        """
        if isinstance(self.mVRT, VRTRaster):
            return self.mVRT.mBands.index(self)
        else:
            return None


    def removeSource(self, vrtRasterInputSourceBand):
        """
        Removes a VRTRasterInputSourceBand
        :param vrtRasterInputSourceBand: band index| VRTRasterInputSourceBand
        :return: The VRTRasterInputSourceBand that was removed
        """
        if isinstance(vrtRasterInputSourceBand, str):
            for sourceBand in self:
                assert isinstance(sourceBand, VRTRasterInputSourceBand)
                if sourceBand.source() == vrtRasterInputSourceBand:
                    vrtRasterInputSourceBand  = sourceBand
                    break


        if isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand) and vrtRasterInputSourceBand in self.mSources:
            i = self.mSources.index(vrtRasterInputSourceBand)
            self.mSources.remove(vrtRasterInputSourceBand)
            self.sigSourceRemoved.emit(i, vrtRasterInputSourceBand)


    def sourceFiles(self)->list:
        """
        Returns the files paths of source files
        :return: [list-of-str]
        """
        files = []
        for inputSourceBand in self.mSources:
            assert isinstance(inputSourceBand, VRTRasterInputSourceBand)
            if inputSourceBand.source() not in files:
                files.append(inputSourceBand.source())
        return files

    def __repr__(self):
        infos = ['VirtualBand name="{}"'.format(self.mName)]
        for i, info in enumerate(self.mSources):
            assert isinstance(info, VRTRasterInputSourceBand)
            infos.append('\t{} SourceFileName {} SourceBand {}'.format(i + 1, info.mSource, info.mBandIndex))
        return '\n'.join(infos)


class VRTRaster(QObject):

    sigSourceBandInserted = pyqtSignal(VRTRasterBand, VRTRasterInputSourceBand)
    sigSourceBandRemoved = pyqtSignal(VRTRasterBand, VRTRasterInputSourceBand)
    sigBandInserted = pyqtSignal(int, VRTRasterBand)
    sigBandRemoved = pyqtSignal(int, VRTRasterBand)
    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)
    sigResolutionChanged = pyqtSignal()
    sigResamplingAlgChanged = pyqtSignal([str],[int])
    sigExtentChanged = pyqtSignal()
    sigNoDataValueChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super(VRTRaster, self).__init__(parent)
        self.mBands = []
        self.mCrs = None
        self.mResamplingAlg = gdal.GRA_NearestNeighbour
        self.mMetadata = dict()
        self.mUL = None
        self.mResolution = None
        self.mSize = None
        self.mNoDataValue = None
        self.sigSourceBandInserted.connect(self.checkBasicParameters)


    def checkBasicParameters(self, vrtBand:VRTRasterBand):

        if len(vrtBand) == 0:
            return

        if not (isinstance(self.crs(), QgsCoordinateReferenceSystem) and
                isinstance(self.extent(), QgsRectangle) and
                isinstance(self.resolution(), QSizeF)):
            lyr = vrtBand[0].toRasterLayer()
            assert isinstance(lyr, QgsRasterLayer), 'Unable to open {} as QgsRasterLayer'.format(vrtBand[0])

            if not isinstance(self.mCrs, QgsCoordinateReferenceSystem):
                self.setCrs(lyr.crs())

            if not isinstance(self.mResolution, QSizeF):
                res = resolution(lyr)
                self.setResolution(res)

            if not isinstance(self.ul(), QgsPointXY):
                ext = lyr.extent()
                self.mUL = QgsPointXY(ext.xMinimum(), ext.yMaximum())

            if not isinstance(self.size(), QSize):
                self.setSize(QSize(lyr.width(), lyr.height()))

    def alignToRasterGrid(self, reference, crop:bool=False):
        """
        Aligns the VRT raster grid to that in source
        :param reference: str path | gdal.Dataset | QgsRasterLayer
        :param crop: bool, optional, set True to crop or enlarge the VRT extent to that of the reference raster.
        """
        lyr = toRasterLayer(reference)
        assert isinstance(lyr, QgsRasterLayer)
        newCRS = lyr.crs()
        oldCRS = self.crs()
        newRes = QSizeF(lyr.rasterUnitsPerPixelY(), lyr.rasterUnitsPerPixelY())
        self.setCrs(newCRS)
        self.setResolution(newRes)
        ext = lyr.extent()
        ulRef = QgsPointXY(ext.xMinimum(), ext.yMaximum())
        if crop:
            lrRef = QgsPointXY(ext.xMaximum(), ext.yMinimum())
            newExtent = QgsRectangle(ulRef, lrRef)
        else:
            newExtent, px = alignRectangleToGrid(newRes, ulRef, self.extent())
        self.setExtent(newExtent, newCRS, ulRef)
        s = ""

    def alignToGrid(self, pxSize:QSizeF, refPoint:QgsPointXY):
        """
        Aligns the given VRT grid (defined by spatial extent and resolution) to the grid definde by pxSite and refPoint.
        :param pxSize: QSizeF, new pixel resolution
        :param refPoint: QgsPointXY, point int the new grid
        """
        ext = self.extent()
        ext2 = alignRectangleToGrid(pxSize, refPoint, ext)
        self.setExtent(ext2)

    def setResamplingAlg(self, value):
        """
        Sets the resampling algorithm
        :param value:
            - Any gdal.GRA_* constant, like gdal.GRA_NearestNeighbor
            - nearest,bilinear,cubic,cubicspline,lanczos,average,mode
            - None (will set the default value to 'nearest'
        """
        last = self.mResamplingAlg

        possibleNames = RESAMPLE_ALGS.optionNames()
        possibleValues = RESAMPLE_ALGS.optionValues()

        if value is None:
            self.mResamplingAlg = gdal.GRA_NearestNeighbour
        elif value in possibleNames:
            self.mResamplingAlg = possibleValues[possibleNames.index(value)]
        elif value in possibleValues:
            self.mResamplingAlg = value
        else:
            raise Exception('Unknown value "{}"'.format(value))
        if last != self.mResamplingAlg:
            self.sigResamplingAlgChanged[str].emit(self.resamplingAlg(asString=True))
            self.sigResamplingAlgChanged[int].emit(self.resamplingAlg())


    def resamplingAlg(self, asString=False):
        """
        "Returns the resampling algorithms.
        :param asString: Set True to return the resampling algorithm as string.
        :return:  gdal.GRA* constant | str with name.
        """
        if asString:
            i = RESAMPLE_ALGS.optionValues().index(self.mResamplingAlg)

            return RESAMPLE_ALGS.optionNames()[i]
        else:
            return self.mResamplingAlg


    def setNoDataValue(self, value):
        """
        Sets the image no data value, which will be applied to each single band
        :param value: float | None
        """
        assert isinstance(value, (None, float))
        if self.mNoDataValue != value:
            self.mNoDataValue = value
            self.sigNoDataValueChanged.emit(value)

    def noDataValue(self)->float:
        """
        Returns the image no data value
        :return: float
        """
        return self.mNoDataValue

    def setExtent(self, rectangle:QgsRectangle, crs:QgsCoordinateReferenceSystem=None, referenceGrid:QgsPointXY=None):
        """
        Sets a new extent. This will change the number of pixels
        :param rectangle: QgsRectangle
        :param crs: QgsCoordinateReferenceSystem of coordinate in rectangle.
        """
        
        
        last = self.extent()

        if not isinstance(crs, QgsCoordinateReferenceSystem):
            crs = self.mCrs

        if isinstance(crs, QgsCoordinateReferenceSystem):
            assert isinstance(self.mCrs, QgsCoordinateReferenceSystem), 'use .setCrs() to specific the VRT coordinate reference system first'
            if crs != self.mCrs:
                trans = QgsCoordinateTransform()
                trans.setSourceCrs(crs)
                trans.setDestinationCrs(self.mCrs)
                rectangle = transformBoundingBox(rectangle, trans)

                if isinstance(referenceGrid, QgsPointXY):
                    referenceGrid = trans.transform(referenceGrid)

        assert isinstance(rectangle, QgsRectangle)
        if not (rectangle.isFinite() and rectangle.width() > 0 and rectangle.height() > 0):
            return 

        # align to pixel size
        if not isinstance(referenceGrid, QgsPointXY):
            referenceGrid = QgsPointXY(rectangle.xMinimum(), rectangle.yMaximum())
        
        res = self.resolution()
        if isinstance(res, QSizeF):
            extent, px = alignRectangleToGrid(res, referenceGrid, rectangle)
            self.mUL = QgsPointXY(extent.xMinimum(), extent.yMaximum())
            self.setSize(px)
            
            if last != extent:
                self.sigExtentChanged.emit()



    def size(self)->QSize:
        """
        Returns the raster size in pixel
        :return: QSize
        """
        return self.mSize

    def setSize(self, size:QSize):
        """
        Sets the raster size in pixel. Requires to have resolution, CRS and extent set and will calculate a new
        extent
        :param size: QSize, the new raster size
        """
        assert size.width() > 0
        assert size.height() > 0

        if self.mSize != size:
            self.mSize = size
            self.sigExtentChanged.emit()

    def ul(self)->QgsPointXY:
        """
        Returns the upper-left image pixel corner coordinate.

        :return: QgsPointXY
        """
        return self.mUL

    def lr(self)->QgsPointXY:
        """
        Returns the lower-right image pixel corner coordinate.

        :return: QgsPointXY
        """
        size = self.size()
        res = self.resolution()
        ul = self.ul()

        if None in [size, res, ul]:
            return None

        lr = QgsPointXY(ul.x() + size.width() * res.width(),
                        ul.y() - size.height() * res.height())
        return lr

    def outputBounds(self)->tuple:
        """
        Returns a bounds tuple.
        :return: tuple (xMin, yMin, xMax, yMax)
        """
        ul = self.ul()
        lr = self.lr()
        return (ul.x(), lr.y(), lr.x(), ul.y())

    def extent(self)->QgsRectangle:
        """
        Returns the spatial extent
        :return: QgsRectangle
        """

        ul = self.ul()
        lr = self.lr()
        if ul is None or lr is None:
            return None
        return QgsRectangle(ul.x(), lr.y(), lr.x(), ul.y())

    def setResolution(self, resolution, crs:QgsCoordinateReferenceSystem=None):
        """
        Set the VRT resolution.
        :param resolution: explicit value given as QSizeF(x,y) object or
                   implicit as 'highest','lowest','average'
        """
        last = self.resolution()

        if resolution is None:
            resolution = 'average'

        if isinstance(resolution, str):
            #find source resolutions
            res = []
            self.sourceRaster()


        else:
            if isinstance(resolution, QSizeF):
                assert resolution.width() > 0
                assert resolution.height() > 0

                if isinstance(self.crs(), QgsCoordinateReferenceSystem) and isinstance(crs, QgsCoordinateReferenceSystem):
                    muSrc = crs.mapUnits()
                    muDst = self.crs().mapUnits()
                    if muSrc != muDst:
                        #convert resolution into target units

                        trans = QgsCoordinateTransform()
                        trans.setSourceCrs(crs)
                        trans.setDestinationCrs(self.crs())
                        ulSrc = trans.transform(self.ul(), direction=QgsCoordinateTransform.ReverseTransform)
                        lrSrc = QgsPointXY(ulSrc.x() + resolution.width(), ulSrc.y() + resolution.height())
                        vect = self.ul() - trans.transform(lrSrc)

                        resolution = QSizeF(abs(vect.x()), abs(vect.y()))






                self.mResolution = QSizeF(resolution)
                #adjust extent
                s = ""

            elif isinstance(resolution, str):
                assert resolution in ['average', 'highest', 'lowest']
                self.mResolution = resolution

        if last != self.mResolution:
            self.sigResolutionChanged.emit()

    def resolution(self)->QSizeF:
        """
        Returns the internal resolution / pixel size
        :return: QSizeF
        """
        if isinstance(self.mResolution, QSizeF):
            return self.mResolution
        elif self.mResolution == 'average':
            pass
        elif self.mResolution == 'min':
            pass
        elif self.mResolution == 'max':
            pass
        return None


    def setCrs(self, crs, warpArgs:dict=None):
        """
        Sets the output Coordinate Reference System (CRS). The UL coordinate will be reprojected to automatically to new CRS
         and the LR is calculated using the resolution and former pixel size. The new image will have at least a size of 1x1 pixel
        :param crs: osr.SpatialReference or QgsCoordinateReferenceSystem
        """
        if isinstance(crs, osr.SpatialReference):
            auth = '{}:{}'.format(crs.GetAttrValue('AUTHORITY', 0), crs.GetAttrValue('AUTHORITY',1))
            crs = QgsCoordinateReferenceSystem(auth)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        if crs != self.crs():
            crsOld = self.crs()
            crsNew = crs

            self.mCrs = crs

            try:
                if isinstance(crsOld, QgsCoordinateReferenceSystem) and isinstance(self.size(), QSize):
                    drvVRT = gdal.GetDriverByName('VRT')
                    id = uuid.uuid4()
                    tmpSrc = '/vsimem/tmp.{}.src.vrt'.format(id)
                    tmpDst = '/vsimem/tmp.{}.dst.vrt'.format(id)

                    dsVRTDummySrc = drvVRT.Create(tmpSrc, self.size().width(), self.size().height(), 1, eType=gdal.GDT_Byte)
                    dsVRTDummySrc.SetProjection(crsOld.toWkt())
                    dsVRTDummySrc.SetGeoTransform(geotransform(self.ul(), self.resolution()))
                    dsVRTDummySrc.FlushCache()

                    if not isinstance(warpArgs, dict):
                        warpArgs = dict()

                    wops = gdal.WarpOptions(dstSRS=crsNew.toWkt(),
                                            #outputBoundsSRS=self.srs(), #keep same bounds
                                            #outputBounds=self.outputBounds(),
                                            format='VRT',
                                            **warpArgs)

                    dsVRTWarped = gdal.Warp(tmpDst, dsVRTDummySrc, options=wops)
                    gdal.Unlink(tmpSrc)

                    if not isinstance(dsVRTWarped, gdal.Dataset):

                        trans = QgsCoordinateTransform()
                        trans.setSourceCrs(crsOld)
                        trans.setDestinationCrs(crsNew)

                        ul2 = trans.transform(self.ul())
                        lr2 = trans.transform(self.lr())
                        raise Exception('Warping failed from \n{} \nto {}'.format(self.crs().description(), crs.description()))

                    gt = dsVRTWarped.GetGeoTransform()
                    ul = px2geo(QgsPoint(0, 0), gt)
                    size = QSize(dsVRTWarped.RasterXSize, dsVRTWarped.RasterYSize)
                    res = resolution(dsVRTWarped)
                    # clean
                    dsVRTDummySrc = dsVRTWarped = None

                    gdal.Unlink(tmpDst)

                    # set new image properties
                    self.mUL = ul
                    self.mSize = size
                    self.mResolution = res
                    self.sigExtentChanged.emit()
            except Exception as ex:
                print(ex, file=sys.stderr)

            self.sigCrsChanged.emit(self.mCrs)

    def crs(self)->QgsCoordinateReferenceSystem:
        """
        Returns the raster coordinate reference system / projection system
        :return: QgsCoordinateReferenceSystem
        """
        return self.mCrs

    def srs(self)->osr.SpatialReference:
        """
        Returns the raster coordinate reference system / projection system as osr.SpatialReference
        :return: osr.SpatialReference
        """
        if not isinstance(self.mCrs, QgsCoordinateReferenceSystem):
            return None
        srs = osr.SpatialReference()
        srs.ImportFromWkt(self.mCrs.toWkt())
        return srs

    def addVirtualBand(self, virtualBand:VRTRasterBand):
        """
        Adds a virtual band
        :param virtualBand: VRTRasterBand
        :return: VirtualBand
        """
        assert isinstance(virtualBand, VRTRasterBand)
        return self.insertVirtualBand(len(self), virtualBand)

    def insertSourceBand(self, virtualBandIndex:int, pathSource, sourceBandIndex:int):
        """
        Inserts a source band into the VRT stack
        :param virtualBandIndex: target virtual band index
        :param pathSource: path of source file
        :param sourceBandIndex: source file band index
        """

        while virtualBandIndex > len(self.mBands)-1:

            self.insertVirtualBand(len(self.mBands), VRTRasterBand())

        vBand = self.mBands[virtualBandIndex]
        vBand.addSourceBand(pathSource, sourceBandIndex)


    def insertVirtualBand(self, index:int, virtualBand:VRTRasterBand):
        """
        Inserts a VirtualBand
        :param index: the insert position
        :param virtualBand: the VirtualBand to be inserted
        :return: the VirtualBand
        """
        assert isinstance(virtualBand, VRTRasterBand)
        assert index <= len(self.mBands)
        if len(virtualBand.name()) == 0:
            virtualBand.setName('Band {}'.format(index+1))
        virtualBand.mVRT = self

        virtualBand.sigSourceInserted.connect(
            lambda _, sourceBand: self.sigSourceBandInserted.emit(virtualBand, sourceBand))
        virtualBand.sigSourceRemoved.connect(
            lambda _, sourceBand: self.sigSourceBandInserted.emit(virtualBand, sourceBand))


        self.mBands.insert(index, virtualBand)
        self.checkBasicParameters(virtualBand)
        self.sigBandInserted.emit(index, virtualBand)

        return self[index]



    def removeVirtualBands(self, bandsOrIndices):
        assert isinstance(bandsOrIndices, list)
        to_remove = []
        for virtualBand in bandsOrIndices:
            if not isinstance(virtualBand, VRTRasterBand):
                virtualBand = self.mBands[virtualBand]
            to_remove.append((self.mBands.index(virtualBand), virtualBand))

        to_remove = sorted(to_remove, key=lambda t: t[0], reverse=True)
        for index, virtualBand in to_remove:
            self.mBands.remove(virtualBand)
            self.sigBandRemoved.emit(index, virtualBand)


    def removeInputSource(self, path:str):
        """
        Removes all bands that relate to a input source image.
        :param path: str, path of input source image
        """
        assert path in self.sourceRaster()
        for vBand in self.mBands:
            assert isinstance(vBand, VRTRasterBand)
            if path in vBand.sourceFiles():
                vBand.removeSource(path)

    def removeVirtualBand(self, bandOrIndex):
        """
        Removes a single
        :param bandOrIndex: int |VRTRasterBand
        """
        self.removeVirtualBands([bandOrIndex])

    def addFilesAsMosaic(self, files):
        """
        Shortcut to mosaic all input files. All bands will maintain their band position in the virtual file.
        :param files: [list-of-file-paths]
        """

        for file in files:
            ds = gdal.Open(file)
            assert isinstance(ds, gdal.Dataset)
            nb = ds.RasterCount
            for b in range(nb):
                if b+1 > len(self):
                    #add new virtual band
                    self.addVirtualBand(VRTRasterBand())
                vBand = self[b]
                assert isinstance(vBand, VRTRasterBand)
                vBand.addSource(VRTRasterInputSourceBand(file, b))
        return self

    def addFilesAsStack(self, files:list):
        """
        Shortcut to stack all input files, i.e. each band of an input file will be a new virtual band.
        Bands in the virtual file will be ordered as file1-band1, file1-band n, file2-band1, file2-band,...
        :param files: [list-of-file-paths]
        :return: self
        """
        assert isinstance(files, list)
        for file in files:
            ds = toDataset(file)
            assert isinstance(ds, gdal.Dataset), 'Can not open {} as gdal.Dataset'.format(file)
            nb = ds.RasterCount
            ds = None
            for b in range(nb):
                #each new band is a new virtual band
                vBand = self.addVirtualBand(VRTRasterBand())
                assert isinstance(vBand, VRTRasterBand)
                vBand.addSource(VRTRasterInputSourceBand(file, b))


        return self

    def sourceRaster(self)->list:
        """
        Returns the list of source raster files.
        :return: [list-of-str]
        """
        files = []
        for vBand in self:
            assert isinstance(vBand, VRTRasterBand)
            for file in vBand.sourceFiles():
                if file not in files:
                    files.append(file)
        return files

    def fullSourceRasterExtent(self)->QgsRectangle:
        """
        Returns a list of (str, QgsRectangle)
        :return: [(str, QgsRectangle),...]
        """

        extent = None
        crs = self.crs()
        for src in self.sourceRaster():

            lyr = QgsRasterLayer(src)
            ext = lyr.extent()
            trans = QgsCoordinateTransform()
            trans.setSourceCrs(lyr.crs())
            trans.setDestinationCrs(self.crs())
            ext = trans.transform(ext)
            if not isinstance(extent, QgsRectangle):
                extent = ext
            else:
                extent.combineExtentWith(ext)
        return extent


    def loadVRT(self, pathVRT, bandIndex = None):
        """
        Load the VRT definition in pathVRT and appends it to this VRT
        :param pathVRT:
        """
        if pathVRT in [None,'']:
            return

        if bandIndex is None:
            bandIndex = len(self.mBands)

        ds = gdal.Open(pathVRT)
        assert isinstance(ds, gdal.Dataset)
        assert ds.GetDriver().GetDescription() == 'VRT'

        for b in range(ds.RasterCount):
            srcBand = ds.GetRasterBand(b+1)
            assert isinstance(srcBand, gdal.Band)

            vrtBand = VRTRasterBand(name=srcBand.GetDescription())

            for key, xml in srcBand.GetMetadata(str('vrt_sources')).items():

                tree = ElementTree.fromstring(xml)
                srcPath = tree.find('SourceFilename').text
                srcBandIndex = int(tree.find('SourceBand').text)
                vrtBand.addSource(VRTRasterInputSourceBand(srcPath, srcBandIndex))

            if b == 0:
                noData = vrtBand.GetNoDataValue()
                self.setNoDataValue(noData)

            self.insertVirtualBand(bandIndex, vrtBand)

            bandIndex += 1

    def saveVRT(self, pathVRT)->gdal.Dataset:
        """
        Save the VRT to path.
        If source images need to be warped to the final CRS warped VRT image will be created in a folder <directory>/<basename>+<warpedImageFolder>/

        :param pathVRT: str, path of final VRT.
        :param warpedImageFolder: basename of folder that is created
        :return:
        """
        """
        :param pathVRT: 
        :return:
        """
        sources = self.sourceRaster()
        assert len(sources) >= 1, 'VRT needs to define at least 1 input source'
        assert os.path.splitext(pathVRT)[-1].lower() == '.vrt'

        srcPathLookup = dict()
        srcNodata = None
        inMemory = pathVRT.startswith('/vsimem/')

        if inMemory:
            dirWarped = '/vsimem/'
            #gdal.Mkdir(dirWarped, 1)
        else:
            dirWarped = os.path.join(os.path.splitext(pathVRT)[0] + '.WarpedImages')
            os.makedirs(dirWarped, exist_ok=True)

        dstExtent = self.extent()
        outputBounds = (dstExtent.xMinimum(), dstExtent.yMinimum(), dstExtent.xMaximum(), dstExtent.yMaximum())
        outputBoundsSRS = self.srs()

        for i, pathSrc in enumerate(self.sourceRaster()):
            dsSrc = gdal.Open(pathSrc)
            assert isinstance(dsSrc, gdal.Dataset)
            band = dsSrc.GetRasterBand(1)
            noData = band.GetNoDataValue()
            if noData and srcNodata is None:
                srcNodata = noData

            crs = QgsCoordinateReferenceSystem(dsSrc.GetProjection())

            if crs == self.crs():
                srcPathLookup[pathSrc] = pathSrc
            else:
                #reproject, if necessary, based on VRT
                bn = os.path.basename(pathSrc)
                warpedFileName = 'warped.{}.{}.vrt'.format(bn, uuid.uuid4())
                if inMemory:
                    warpedFileName = dirWarped + warpedFileName
                else:
                    warpedFileName = os.path.join(dirWarped, warpedFileName)

                wops = gdal.WarpOptions(format='VRT',
                                        resampleAlg=self.mResamplingAlg,
                                        outputBounds=outputBounds,
                                        outputBoundsSRS=outputBoundsSRS,
                                        xRes=self.resolution().width(),
                                        yRes=self.resolution().height(),
                                        dstSRS=self.mCrs.toWkt())

                tmp = gdal.Warp(warpedFileName, dsSrc, options=wops)
                assert isinstance(tmp, gdal.Dataset)
                crs = QgsCoordinateReferenceSystem(tmp.GetProjection())
                if not crs == self.crs():
                    s = ""

                srcPathLookup[pathSrc] = warpedFileName


        srcFiles = [srcPathLookup[src] for src in self.sourceRaster()]



        #these need to be set
        ns = nl = gt = crs = eType = None
        res = self.resolution()
        extent = self.extent()

        srs = None
        if isinstance(self.crs(), QgsCoordinateReferenceSystem):
            srs = self.crs().toWkt()

        if len(srcFiles) > 0:
            # 1. build a temporary VRT that describes the spatial proportions of all input sources
            kwds = {}

            if res is None:
                res = 'average'

            if isinstance(res, QSizeF):
                #kwds['resolution'] = 'user'
                kwds['xRes'] = res.width()
                kwds['yRes'] = res.height()
            else:
                assert res in ['highest', 'lowest', 'average']
                kwds['resolution'] = res

            if isinstance(extent, QgsRectangle):
                kwds['outputBounds'] = (extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())
                pass

            if srs is not None:
                kwds['outputSRS'] = srs

            kwds['bandList'] = [1 for _ in srcFiles] # use the first band only.
            kwds['separate'] = True

            vro = gdal.BuildVRTOptions(**kwds)

            pathTemplateVRT = '/vsimem/template.{}.vrt'.format(uuid.uuid4())
            dsVRTDst = gdal.BuildVRT(pathTemplateVRT, srcFiles, options=vro)
            dsVRTDst.FlushCache()
            assert isinstance(dsVRTDst, gdal.Dataset)
            assert isinstance(dsVRTDst.GetFileList(), list)
            if not dsVRTDst.RasterCount == len(srcFiles):
                ds0 = gdal.Open(srcFiles[0])
                res0 = resolution(ds0)
                pUL = px2geo(QPoint(0,0), ds0.GetGeoTransform())
                pLR = px2geo(QPoint(ds0.RasterXSize, ds0.RasterYSize), ds0.GetGeoTransform())
                ex0 = QgsRectangle(pUL, pLR)

                if not (self.extent().contains(ex0) or self.extent().intersects(ex0)):
                    s = ""
                lyr2 = QgsRasterLayer(srcFiles[0])
                assert lyr2.isValid()
                s = ""

            assert dsVRTDst.RasterCount == len(srcFiles)
            ns, nl = dsVRTDst.RasterXSize, dsVRTDst.RasterYSize
            gt = dsVRTDst.GetGeoTransform()

            SOURCE_TEMPLATES = dict()
            for i, srcFile in enumerate(srcFiles):
                band = dsVRTDst.GetRasterBand(i+1)
                if not isinstance(band, gdal.Band):
                    s = ""
                assert isinstance(band, gdal.Band)
                if i == 0:
                    eType = band.DataType
                vrt_sources = dsVRTDst.GetRasterBand(i+1).GetMetadata(str('vrt_sources'))
                assert len(vrt_sources) == 1
                srcXML = vrt_sources['source_0']
                assert os.path.basename(srcFile)+'</SourceFilename>' in srcXML
                assert '<SourceBand>1</SourceBand>' in srcXML
                SOURCE_TEMPLATES[srcFile] = srcXML
            gdal.Unlink(pathTemplateVRT)
            #drvVRT.Delete(pathInMEMVRT)

        else:
            # special case: no source files defined
            ns = nl = 1 #this is the minimum size
            if isinstance(extent, QgsRectangle):
                x0 = extent.xMinimum()
                y1 = extent.yMaximum()
            else:
                x0 = 0
                y1 = 0

            if isinstance(res, QSizeF):
                resx = res.width()
                resy = res.height()
            else:
                resx = 1
                resy = 1

            gt = (x0, resx, 0, y1, 0, -resy)
            eType = gdal.GDT_Float32




        #2. build final VRT from scratch
        drvVRT = gdal.GetDriverByName('VRT')
        assert isinstance(drvVRT, gdal.Driver)
        dsVRTDst = drvVRT.Create(pathVRT, ns, nl, 0, eType=eType)
        assert isinstance(dsVRTDst, gdal.Dataset)
        #2.1. set general properties


        if srs is not None:
            dsVRTDst.SetProjection(srs)
        dsVRTDst.SetGeoTransform(gt)

        #2.2. add virtual bands
        for i, vBand in enumerate(self.mBands):
            assert isinstance(vBand, VRTRasterBand)
            assert dsVRTDst.AddBand(eType, options=['subClass=VRTSourcedRasterBand']) == 0
            vrtBandDst = dsVRTDst.GetRasterBand(i+1)
            assert isinstance(vrtBandDst, gdal.Band)
            vrtBandDst.SetDescription(vBand.name())
            md = {}
            #add all input sources for this virtual band
            for iSrc, sourceInfo in enumerate(vBand.mSources):
                assert isinstance(sourceInfo, VRTRasterInputSourceBand)
                bandIndex = sourceInfo.mBandIndex
                xml = SOURCE_TEMPLATES[srcPathLookup[sourceInfo.mSource]]
                xml = re.sub('<SourceBand>1</SourceBand>', '<SourceBand>{}</SourceBand>'.format(bandIndex+1), xml)
                md['source_{}'.format(iSrc)] = xml
            vrtBandDst.SetMetadata(md, 'vrt_sources')

        assert dsVRTDst.RasterCount == len(self.mBands)
        dsVRTDst.FlushCache()
        #dsVRTDst = None

        #check if we get what we like to get
        dsCheck = gdal.Open(pathVRT)
        assert isinstance(dsCheck, gdal.Dataset)

        return dsCheck

    def __repr__(self):

        info = ['VirtualRasterBuilder: {} bands, {} source files'.format(
            len(self.mBands), len(self.sourceRaster()))]
        for vBand in self.mBands:
            info.append(str(vBand))
        return '\n'.join(info)

    def __len__(self):
        return len(self.mBands)

    def __getitem__(self, slice):
        return self.mBands[slice]

    def __delitem__(self, slice):
        self.removeVirtualBands(self[slice])

    def __contains__(self, item):
        return item in self.mBands

    def __iter__(self):
        return iter(self.mBands)

def createVirtualBandMosaic(bandFiles, pathVRT):
    drv = gdal.GetDriverByName('VRT')

    refPath = bandFiles[0]
    refDS = gdal.Open(refPath)
    ns, nl, nb = refDS.RasterXSize, refDS.RasterYSize, refDS.RasterCount
    noData = refDS.GetRasterBand(1).GetNoDataValue()

    vrtOptions = gdal.BuildVRTOptions(
        # here we can use the options known from http://www.gdal.org/gdalbuildvrt.html
        separate=False
    )
    if len(bandFiles) > 1:
        s =""
    gdal.BuildVRT(pathVRT, bandFiles, options=vrtOptions)
    vrtDS = gdal.Open(pathVRT)
    assert vrtDS.RasterCount == nb
    return vrtDS

def createVirtualBandStack(bandFiles, pathVRT):

    nb = len(bandFiles)

    drv = gdal.GetDriverByName('VRT')

    refPath = bandFiles[0]
    refDS = gdal.Open(refPath)
    ns, nl = refDS.RasterXSize, refDS.RasterYSize
    noData = refDS.GetRasterBand(1).GetNoDataValue()

    vrtOptions = gdal.BuildVRTOptions(
        # here we can use the options known from http://www.gdal.org/gdalbuildvrt.html
        separate=True,
    )
    gdal.BuildVRT(pathVRT, bandFiles, options=vrtOptions)
    vrtDS = gdal.Open(pathVRT)
    assert isinstance(vrtDS, gdal.Dataset)

    assert vrtDS.RasterCount == nb

    #copy band metadata from
    for i in range(nb):
        band = vrtDS.GetRasterBand(i+1)
        band.SetDescription(bandFiles[i])
        band.ComputeBandStats()

        if noData:
            band.SetNoDataValue(noData)

    return vrtDS

