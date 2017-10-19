# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
/***************************************************************************
                              HUB TimeSeriesViewer
                              -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from __future__ import absolute_import
import os, sys, re, pickle, tempfile
from collections import OrderedDict
import tempfile
from osgeo import gdal, osr, ogr
from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *

def px2geo(px, gt):
    #see http://www.gdal.org/gdal_datamodel.html
    gx = gt[0] + px.x()*gt[1]+px.y()*gt[2]
    gy = gt[3] + px.x()*gt[4]+px.y()*gt[5]
    return QgsPoint(gx,gy)


class VRTRasterInputSourceBand(object):
    def __init__(self, path, bandIndex, bandName=''):
        self.mPath = os.path.normpath(path)
        self.mBandIndex = bandIndex
        self.mBandName = bandName
        self.mNoData = None
        self.mVirtualBand = None



    def isEqual(self, other):
        if isinstance(other, VRTRasterInputSourceBand):
            return self.mPath == other.mPath and self.mBandIndex == other.mBandIndex
        else:
            return False

    def __reduce_ex__(self, protocol):

        return self.__class__, (self.mPath, self.mBandIndex, self.mBandName), self.__getstate__()

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop('mVirtualBand')
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def virtualBand(self):
        return self.mVirtualBand


class VRTRasterBand(QObject):
    sigNameChanged = pyqtSignal(str)
    sigSourceInserted = pyqtSignal(int, VRTRasterInputSourceBand)
    sigSourceRemoved = pyqtSignal(int, VRTRasterInputSourceBand)
    def __init__(self, name='', parent=None):
        super(VRTRasterBand, self).__init__(parent)
        self.sources = []
        self.mName = name
        self.mVRT = None


    def setName(self, name):
        oldName = self.mName
        self.mName = name
        if oldName != self.mName:
            self.sigNameChanged.emit(name)

    def name(self):
        return self.mName



    def addSource(self, virtualBandInputSource):
        assert isinstance(virtualBandInputSource, VRTRasterInputSourceBand)
        self.insertSource(len(self.sources), virtualBandInputSource)

    def insertSource(self, index, virtualBandInputSource):
        assert isinstance(virtualBandInputSource, VRTRasterInputSourceBand)
        virtualBandInputSource.mVirtualBand = self
        assert index <= len(self.sources)
        self.sources.insert(index, virtualBandInputSource)
        self.sigSourceInserted.emit(index, virtualBandInputSource)

    def bandIndex(self):
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
        if not isinstance(vrtRasterInputSourceBand, VRTRasterInputSourceBand):
            vrtRasterInputSourceBand = self.sources[vrtRasterInputSourceBand]
        if vrtRasterInputSourceBand in self.sources:
            i = self.sources.index(vrtRasterInputSourceBand)
            self.sources.remove(vrtRasterInputSourceBand)
            self.sigSourceRemoved.emit(i, vrtRasterInputSourceBand)


    def sourceFiles(self):
        """
        :return: list of file-paths to all source files
        """
        files = set([inputSource.mPath for inputSource in self.sources])
        return sorted(list(files))

    def __repr__(self):
        infos = ['VirtualBand name="{}"'.format(self.mName)]
        for i, info in enumerate(self.sources):
            assert isinstance(info, VRTRasterInputSourceBand)
            infos.append('\t{} SourceFileName {} SourceBand {}'.format(i + 1, info.mPath, info.mBandIndex))
        return '\n'.join(infos)

LUT_ReampleAlg = {'nearest': gdal.GRA_NearestNeighbour,
                  'bilinear': gdal.GRA_Bilinear,
                  'mode':gdal.GRA_Mode,
                  'lanczos':gdal.GRA_Lanczos,
                  'average':gdal.GRA_Average,
                  'cubic':gdal.GRA_Cubic,
                  'cubic_spline':gdal.GRA_CubicSpline}




class VRTRaster(QObject):

    sigSourceBandInserted = pyqtSignal(VRTRasterBand, VRTRasterInputSourceBand)
    sigSourceBandRemoved = pyqtSignal(VRTRasterBand, VRTRasterInputSourceBand)
    sigSourceRasterAdded = pyqtSignal(list)
    sigSourceRasterRemoved = pyqtSignal(list)
    sigBandInserted = pyqtSignal(int, VRTRasterBand)
    sigBandRemoved = pyqtSignal(int, VRTRasterBand)
    sigCrsChanged = pyqtSignal(QgsCoordinateReferenceSystem)


    def __init__(self, parent=None):
        super(VRTRaster, self).__init__(parent)
        self.mBands = []
        self.mCrs = None
        self.mResampleAlg = gdal.GRA_NearestNeighbour
        self.mMetadata = dict()
        self.mSourceRasterBounds = dict()
        self.mOutputBounds = None
        self.sigSourceBandRemoved.connect(self.updateSourceRasterBounds)
        self.sigSourceBandInserted.connect(self.updateSourceRasterBounds)
        self.sigBandRemoved.connect(self.updateSourceRasterBounds)
        self.sigBandInserted.connect(self.updateSourceRasterBounds)

    def setCrs(self, crs):
        if isinstance(crs, osr.SpatialReference):
            auth = '{}:{}'.format(crs.GetAttrValue('AUTHORITY',0), crs.GetAttrValue('AUTHORITY',1))
            crs = QgsCoordinateReferenceSystem(auth)
        if isinstance(crs, QgsCoordinateReferenceSystem):
            if crs != self.mCrs:
                self.mCrs = crs
                self.sigCrsChanged.emit(self.mCrs)


    def crs(self):
        return self.mCrs

    def addVirtualBand(self, virtualBand):
        """
        Adds a virtual band
        :param virtualBand: the VirtualBand to be added
        :return: VirtualBand
        """
        assert isinstance(virtualBand, VRTRasterBand)
        return self.insertVirtualBand(len(self), virtualBand)

    def insertSourceBand(self, virtualBandIndex, pathSource, sourceBandIndex):
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


    def insertVirtualBand(self, index, virtualBand):
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


    def removeInputSource(self, path):
        assert path in self.sourceRaster()
        for vBand in self.mBands:
            assert isinstance(vBand, VRTRasterBand)
            if path in vBand.sources():
                vBand.removeSource(path)

    def removeVirtualBand(self, bandOrIndex):
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
                if b+1 < len(self):
                    #add new virtual band
                    self.addVirtualBand(VRTRasterBand())
                vBand = self[b]
                assert isinstance(vBand, VRTRasterBand)
                vBand.addSourceBand(file, b)
        return self

    def addFilesAsStack(self, files):
        """
        Shortcut to stack all input files, i.e. each band of an input file will be a new virtual band.
        Bands in the virtual file will be ordered as file1-band1, file1-band n, file2-band1, file2-band,...
        :param files: [list-of-file-paths]
        :return: self
        """
        for file in files:
            ds = gdal.Open(file)
            assert isinstance(ds, gdal.Dataset), 'Can not open {}'.format(file)
            nb = ds.RasterCount
            ds = None
            for b in range(nb):
                #each new band is a new virtual band
                vBand = self.addVirtualBand(VRTRasterBand())
                assert isinstance(vBand, VRTRasterBand)
                vBand.addSource(VRTRasterInputSourceBand(file, b))


        return self

    def sourceRaster(self):
        files = set()
        for vBand in self.mBands:
            assert isinstance(vBand, VRTRasterBand)
            files.update(set(vBand.sourceFiles()))
        return sorted(list(files))

    def sourceRasterBounds(self):
        return self.mSourceRasterBounds

    def outputBounds(self):
        if isinstance(self.mOutputBounds, RasterBounds):
            return
            #calculate from source rasters

    def setOutputBounds(self, bounds):
        assert isinstance(self, RasterBounds)
        self.mOutputBounds = bounds


    def updateSourceRasterBounds(self):

        srcFiles = self.sourceRaster()
        toRemove = [f for f in self.mSourceRasterBounds.keys() if f not in srcFiles]
        toAdd = [f for f in srcFiles if f not in self.mSourceRasterBounds.keys()]

        for f in toRemove:
            del self.mSourceRasterBounds[f]
        for f in toAdd:
            self.mSourceRasterBounds[f] = RasterBounds(f)

        if len(srcFiles) > 0 and self.crs() == None:
            self.setCrs(self.mSourceRasterBounds[srcFiles[0]].crs)

        elif len(srcFiles) == 0:
            self.setCrs(None)


        if len(toRemove) > 0:
            self.sigSourceRasterRemoved.emit(toRemove)
        if len(toAdd) > 0:
            self.sigSourceRasterAdded.emit(toAdd)

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
        from xml.etree import ElementTree
        for b in range(ds.RasterCount):
            srcBand = ds.GetRasterBand(b+1)
            vrtBand = VRTRasterBand(name=srcBand.GetDescription())
            for key, xml in srcBand.GetMetadata('vrt_sources').items():

                tree = ElementTree.fromstring(xml)
                srcPath = os.path.normpath(tree.find('SourceFilename').text)
                srcBandIndex = int(tree.find('SourceBand').text)
                vrtBand.addSource(VRTRasterInputSourceBand(srcPath, srcBandIndex))

            self.insertVirtualBand(bandIndex, vrtBand)
            bandIndex += 1




    def saveVRT(self, pathVRT, resampleAlg=gdal.GRA_NearestNeighbour, **kwds):
        """
        :param pathVRT: path to VRT that is created
        :param options --- can be be an array of strings, a string or let empty and filled from other keywords..
        :param resolution --- 'highest', 'lowest', 'average', 'user'.
        :param outputBounds --- output bounds as (minX, minY, maxX, maxY) in target SRS.
        :param xRes, yRes --- output resolution in target SRS.
        :param targetAlignedPixels --- whether to force output bounds to be multiple of output resolution.
        :param bandList --- array of band numbers (index start at 1).
        :param addAlpha --- whether to add an alpha mask band to the VRT when the source raster have none.
        :param resampleAlg --- resampling mode.
        :param outputSRS --- assigned output SRS.
        :param allowProjectionDifference --- whether to accept input datasets have not the same projection. Note: they will *not* be reprojected.
        :param srcNodata --- source nodata value(s).
        :param callback --- callback method.
        :param callback_data --- user data for callback.
        :return: gdal.DataSet(pathVRT)
        """

        if len(self.mBands) == 0:
            print('No VRT Inputs defined.')
            return None

        assert os.path.splitext(pathVRT)[-1].lower() == '.vrt'

        _kwds = dict()
        supported = ['options','resolution','outputBounds','xRes','yRes','targetAlignedPixels','addAlpha','resampleAlg',
        'outputSRS','allowProjectionDifference','srcNodata','VRTNodata','hideNodata','callback', 'callback_data']
        for k in kwds.keys():
            if k in supported:
                _kwds[k] = kwds[k]

        if 'resampleAlg' not in _kwds:
            _kwds['resampleAlg'] = resampleAlg

        if isinstance(self.mOutputBounds, RasterBounds):
            bounds = self.mOutputBounds.polygon
            xmin, ymin,xmax, ymax = bounds
            _kwds['outputBounds'] = (xmin, ymin,xmax, ymax)

        dirVrt = os.path.dirname(pathVRT)
        dirWarpedVRT = os.path.join(dirVrt, 'WarpedVRTs')
        if not os.path.isdir(dirVrt):
            os.mkdir(dirVrt)

        srcLookup = dict()
        srcNodata = None
        for i, pathSrc in enumerate(self.sourceRaster()):
            dsSrc = gdal.Open(pathSrc)
            assert isinstance(dsSrc, gdal.Dataset)
            band = dsSrc.GetRasterBand(1)
            noData = band.GetNoDataValue()
            if noData and srcNodata is None:
                srcNodata = noData

            crs = QgsCoordinateReferenceSystem(dsSrc.GetProjection())

            if crs == self.mCrs:
                srcLookup[pathSrc] = pathSrc
            else:

                if not os.path.isdir(dirWarpedVRT):
                    os.mkdir(dirWarpedVRT)
                pathVRT2 = os.path.join(dirWarpedVRT, 'warped.{}.vrt'.format(os.path.basename(pathSrc)))
                wops = gdal.WarpOptions(format='VRT',
                                        dstSRS=self.mCrs.toWkt())
                tmp = gdal.Warp(pathVRT2, dsSrc, options=wops)
                assert isinstance(tmp, gdal.Dataset)
                tmp = None
                srcLookup[pathSrc] = pathVRT2




        srcFiles = [srcLookup[src] for src in self.sourceRaster()]

        vro = gdal.BuildVRTOptions(separate=True, **_kwds)
        #1. build a temporary VRT that described the spatial shifts of all input sources
        gdal.BuildVRT(pathVRT, srcFiles, options=vro)
        dsVRTDst = gdal.Open(pathVRT)
        assert isinstance(dsVRTDst, gdal.Dataset)
        assert len(srcLookup) == dsVRTDst.RasterCount
        ns, nl = dsVRTDst.RasterXSize, dsVRTDst.RasterYSize
        gt = dsVRTDst.GetGeoTransform()
        crs = dsVRTDst.GetProjectionRef()
        eType = dsVRTDst.GetRasterBand(1).DataType
        SOURCE_TEMPLATES = dict()
        for i, srcFile in enumerate(srcFiles):
            vrt_sources = dsVRTDst.GetRasterBand(i+1).GetMetadata('vrt_sources')
            assert len(vrt_sources) == 1
            srcXML = vrt_sources.values()[0]
            assert os.path.basename(srcFile)+'</SourceFilename>' in srcXML
            assert '<SourceBand>1</SourceBand>' in srcXML
            SOURCE_TEMPLATES[srcFile] = srcXML
        dsVRTDst = None
        #remove the temporary VRT, we don't need it any more
        os.remove(pathVRT)

        #2. build final VRT from scratch
        drvVRT = gdal.GetDriverByName('VRT')
        assert isinstance(drvVRT, gdal.Driver)
        dsVRTDst = drvVRT.Create(pathVRT, ns, nl,0, eType=eType)
        #2.1. set general properties
        assert isinstance(dsVRTDst, gdal.Dataset)
        dsVRTDst.SetProjection(crs)
        dsVRTDst.SetGeoTransform(gt)

        #2.2. add virtual bands
        for i, vBand in enumerate(self.mBands):
            assert isinstance(vBand, VRTRasterBand)
            assert dsVRTDst.AddBand(eType, options=['subClass=VRTSourcedRasterBand']) == 0
            vrtBandDst = dsVRTDst.GetRasterBand(i+1)
            assert isinstance(vrtBandDst, gdal.Band)
            vrtBandDst.SetDescription(str(vBand.name()))
            md = {}
            #add all input sources for this virtual band
            for iSrc, sourceInfo in enumerate(vBand.sources):
                assert isinstance(sourceInfo, VRTRasterInputSourceBand)
                bandIndex = sourceInfo.mBandIndex
                xml = SOURCE_TEMPLATES[srcLookup[sourceInfo.mPath]]
                xml = re.sub('<SourceBand>1</SourceBand>','<SourceBand>{}</SourceBand>'.format(bandIndex+1), xml)
                md['source_{}'.format(iSrc)] = xml
            vrtBandDst.SetMetadata(md,'vrt_sources')
            if False:
                vrtBandDst.ComputeBandStats(1)


        dsVRTDst = None

        #check if we get what we like to get
        dsCheck = gdal.Open(pathVRT)

        s = ""
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
        return iter(self.mClasses)





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
    vrtDS = gdal.BuildVRT(pathVRT, bandFiles, options=vrtOptions)
    vrtDS.FlushCache()

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
    vrtDS = gdal.BuildVRT(pathVRT, bandFiles, options=vrtOptions)
    vrtDS.FlushCache()

    assert vrtDS.RasterCount == nb

    #copy band metadata from
    for i in range(nb):
        band = vrtDS.GetRasterBand(i+1)
        band.SetDescription(bandFiles[i])
        band.ComputeBandStats()

        if noData:
            band.SetNoDataValue(noData)

    return vrtDS



class RasterBounds(object):
    def __init__(self, path):
        self.path = None
        self.polygon = None
        self.curve = None
        self.crs = None

        if path is not None:
            self.fromImage(path)

    def fromRectangle(self, crs, rectangle):
        assert isinstance(rectangle, QgsRectangle)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.crs = crs
        self.path = ''
        s = ""


    def fromImage(self, path):
        self.path = path
        ds = gdal.Open(path)
        assert isinstance(ds, gdal.Dataset)
        gt = ds.GetGeoTransform()
        bounds = [px2geo(QPoint(0, 0), gt),
                  px2geo(QPoint(ds.RasterXSize, 0), gt),
                  px2geo(QPoint(ds.RasterXSize, ds.RasterYSize), gt),
                  px2geo(QPoint(0, ds.RasterYSize), gt)]
        crs = QgsCoordinateReferenceSystem(ds.GetProjection())
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for p in bounds:
            assert isinstance(p, QgsPoint)
            ring.AddPoint(p.x(), p.y())

        curve = ogr.Geometry(ogr.wkbLinearRing)
        curve.AddGeometry(ring)
        self.curve = QgsCircularStringV2()
        self.curve.fromWkt(curve.ExportToWkt())

        polygon = ogr.Geometry(ogr.wkbPolygon)
        polygon.AddGeometry(ring)
        self.polygon = QgsPolygonV2()
        self.polygon.fromWkt(polygon.ExportToWkt())
        self.polygon.exteriorRing().close()
        assert self.polygon.exteriorRing().isClosed()

        self.crs = crs

    def __repr__(self):
        return self.polygon.ExportToWkt()


if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from vrtbuilder import utils
    from vrtbuilder.widgets import VRTBuilderWidget
    qgsApp = utils.initQgisApplication()

    if False:
        r = VRTRaster()
        p = r'D:\Repositories\QGIS_Plugins\hub-timeseriesviewer\test\output.vrt'
        r.loadVRT(p)

        exit(0)

    w = VRTBuilderWidget()

    import sys

    if sys.platform == 'darwin':
        files = [
        r'/Users/Shared/Multitemp2017/01_Data/RapidEye/re_2012-07-25.vrt'
        #p2 = r'/Users/Shared/Multitemp2017/01_Data/Landsat/LC82270652014207LGN00.vrt'
        ,r'/Users/Shared/Multitemp2017/01_Data/CBERS/CBERS_4_MUX_20150820.vrt'
        ]

    else:
        files = [
        r'S:/temp/temp_ar/4benjamin/05_CBERS/CBERS_4_MUX_20150603_167_107_L4_BAND5_GRID_SURFACE.tif'
        #,r'D:/Repositories/QGIS_Plugins/hub-timeseriesviewer/example/Images/re_2014-06-25.tif'
        ,r'D:/Repositories/QGIS_Plugins/hub-timeseriesviewer/example/Images/2014-08-27_LC82270652014239LGN00_BOA.tif'
        ]

    w.addSourceFiles(files)
    #w.vrtRaster.addFilesAsStack([p1, p2, p3])
    p = r'S:/temp/temp_ar/4benjamin/05_CBERS/CBERS_4_MUX_20150603_167_107_L4_BAND5_GRID_SURFACE.tif'
    bLyr = QgsRasterLayer(p, 'backgroud', 'gdal', True)
    QgsMapLayerRegistry.instance().addMapLayer(bLyr)

    #w.setBackgroundLayer(bLyr)
    w.show()


    qgsApp.exec_()
    qgsApp.exitQgis()
