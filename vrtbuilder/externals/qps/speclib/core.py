# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/core.py

    Spectral Profiles and Libraries for QGIS.
    ---------------------
    Date                 : Juli 2017
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""

# see http://python-future.org/str_literals.html for str issue discussion
import json
import enum
import pickle
import typing
import pathlib
from osgeo import osr
from ..speclib import SpectralLibrarySettingsKey
from PyQt5.QtWidgets import *
from qgis.core import \
    QgsRenderContext, QgsFeature, QgsVectorLayer, QgsMapLayer, QgsRasterLayer, \
    QgsAttributeTableConfig, QgsField, QgsFields, QgsCoordinateReferenceSystem, QgsCoordinateTransform, \
    QgsVectorFileWriter, QgsActionManager, QgsFeatureIterator, QgsFeatureRequest, \
    QgsGeometry, QgsPointXY, QgsPoint, QgsMultiPoint, \
    QgsRaster, QgsDefaultValue, QgsReadWriteContext, \
    QgsCategorizedSymbolRenderer, QgsMapLayerProxyModel, \
    QgsSymbol, QgsNullSymbolRenderer, QgsMarkerSymbol, QgsLineSymbol, QgsFillSymbol, \
    QgsEditorWidgetSetup, QgsAction

from qgis.gui import \
    QgsGui, QgsMapCanvas, QgsDualView, QgisInterface, QgsEditorConfigWidget, \
    QgsEditorWidgetWrapper, QgsActionMenu, QgsEditorWidgetFactory, QgsDockWidget

from ..utils import *
from ..plotstyling.plotstyling import PlotStyle
from ..speclib import speclibSettings, EDITOR_WIDGET_REGISTRY_KEY

# get to now how we can import this module
MODULE_IMPORT_PATH = None
XMLNODE_PROFILE_RENDERER = 'spectralProfileRenderer'

for name, module in sys.modules.items():
    if hasattr(module, '__file__') and module.__file__ == __file__:
        MODULE_IMPORT_PATH = name
        break

MIMEDATA_SPECLIB = 'application/hub-spectrallibrary'
MIMEDATA_SPECLIB_LINK = 'application/hub-spectrallibrary-link'
MIMEDATA_XQT_WINDOWS_CSV = 'application/x-qt-windows-mime;value="Csv"'

# see https://doc.qt.io/qt-5/qwinmime.html
MIMEDATA_TEXT = 'text/plain'
MIMEDATA_URL = 'text/uri-list'

SPECLIB_EPSG_CODE = 4326
SPECLIB_CRS = QgsCoordinateReferenceSystem('EPSG:{}'.format(SPECLIB_EPSG_CODE))

SPECLIB_CLIPBOARD = weakref.WeakValueDictionary()
DEFAULT_NAME = 'SpectralLibrary'

OGR_EXTENSION2DRIVER = dict()
OGR_EXTENSION2DRIVER[''] = []  # list all drivers without specific extension

for i in range(ogr.GetDriverCount()):
    drv = ogr.GetDriver(i)
    extensions = drv.GetMetadataItem(gdal.DMD_EXTENSIONS)
    if isinstance(extensions, str):
        extensions = extensions.split(',')
        for ext in extensions:
            if ext not in OGR_EXTENSION2DRIVER.keys():
                OGR_EXTENSION2DRIVER[ext] = []
            OGR_EXTENSION2DRIVER[ext].append(drv.GetName())
    else:
        OGR_EXTENSION2DRIVER[''].append(drv.GetName())
OGR_EXTENSION2DRIVER[None] = OGR_EXTENSION2DRIVER['']

DEBUG = False


class SerializationMode(enum.Enum):
    JSON = 1
    PICKLE = 2


SERIALIZATION = SerializationMode.PICKLE


def log(msg: str):
    if DEBUG:
        QgsMessageLog.logMessage(msg, 'spectrallibraries.py')


def containsSpeclib(mimeData: QMimeData) -> bool:
    for f in [MIMEDATA_SPECLIB, MIMEDATA_SPECLIB_LINK]:
        if f in mimeData.formats():
            return True

    return False


FILTERS = 'ENVI Spectral Library (*.sli *.esl);;CSV Table (*.csv);;Geopackage (*.gpkg);;GeoJSON (*.geojson)'

PICKLE_PROTOCOL = pickle.HIGHEST_PROTOCOL
# CURRENT_SPECTRUM_STYLE = PlotStyle()
# CURRENT_SPECTRUM_STYLE.markerSymbol = None
# CURRENT_SPECTRUM_STYLE.linePen.setStyle(Qt.SolidLine)
# CURRENT_SPECTRUM_STYLE.linePen.setColor(Qt.green)


# DEFAULT_SPECTRUM_STYLE = PlotStyle()
# DEFAULT_SPECTRUM_STYLE.markerSymbol = None
# DEFAULT_SPECTRUM_STYLE.linePen.setStyle(Qt.SolidLine)
# DEFAULT_SPECTRUM_STYLE.linePen.setColor(Qt.white)

EMPTY_VALUES = [None, NULL, QVariant(), '', 'None']
EMPTY_PROFILE_VALUES = {'x': None, 'y': None, 'xUnit': None, 'yUnit': None, 'bbl': None}

FIELD_VALUES = 'values'
FIELD_NAME = 'name'
FIELD_FID = 'fid'

VSI_DIR = r'/vsimem/speclibs/'
X_UNITS = ['Index', 'Micrometers', 'Nanometers', 'Millimeters', 'Centimeters', 'Meters', 'Wavenumber', 'Angstroms',
           'GHz', 'MHz', '']
Y_UNITS = ['DN', 'Reflectance', 'Radiance', '']


def speclibUiPath(name: str) -> str:
    """
    Returns the path to a spectral library *.ui file
    :param name: name
    :type name: str
    :return: absolute path to *.ui file
    :rtype: str
    """
    path = pathlib.Path(__file__).parent / name
    assert path.is_file()
    return path.as_posix()


class ProgressHandler(QObject):
    """
    A class that mimics the QProgressDialog's functions to report progress.
    Can be used e.g. in parallel threads if progress needs to be reported outside the main gui thread.
    """
    canceled = pyqtSignal()
    progressChanged = pyqtSignal([int], [int, int, int])

    def __init__(self, *args, **kwds):
        super().__init__()

        self.mMinimum: int = int(kwds.get('minimum', 0))
        self.mMaximum: int = int(kwds.get('maximum', 0))
        self.mValue: int = 0
        self.mLabelText: str = ''
        self.mWasCanceled = False

    def setValue(self, value: int):
        assert isinstance(value, int)
        self.mValue = value
        self.progressChanged[int].emit(value)
        self.progressChanged[int, int, int].emit(self.mMinimum, self.mMaximum, self.mValue)

    def value(self) -> int:
        return self.mValue

    def cancel(self):
        self.mWasCanceled = True
        self.canceled.emit()

    def wasCanceled(self) -> bool:
        return self.mWasCanceled

    def setAutoClose(self):
        pass

    def autoClose(self):
        return True

    def setAutoReset(self):
        pass

    def autoReset(self):
        return False

    def setBar(self, bar):
        pass

    def setCancelButto(self, btn):
        pass

    def setLabel(self, label):
        pass

    def reset(self):
        pass

    def setLabelText(self, text: str):
        self.mLabelText = str(text)

    def labelText(self):
        return self.mLabelText()

    def setRange(self, vMin: int, vMax: int):
        assert vMin <= vMax
        self.setMinimum(vMin)
        self.setMaximum(vMax)

    def setMaximum(self, v: int):
        assert isinstance(v, int)
        self.mMaximum = v

    def setMinimum(self, v: int):
        assert isinstance(v, int)
        self.mMinimum = v

    def setMinimumDuration(self, *args):
        pass

    def setCancelButtonText(self, *args):
        pass


def vsiSpeclibs() -> list:
    """
    Returns the URIs pointing on VSIMEM in memory speclibs
    :return: [list-of-str]
    """
    visSpeclibs = []

    entry = gdal.ReadDir(VSI_DIR)
    if entry is not None:
        for bn in entry:
            p = pathlib.PurePosixPath(VSI_DIR) / bn
            p = p.as_posix()
            stats = gdal.VSIStatL(p)
            if isinstance(stats, gdal.StatBuf) and not stats.IsDirectory():
                visSpeclibs.append(p)
    return visSpeclibs


def runRemoveFeatureActionRoutine(layerID, id: int):
    """
    Is applied to a set of layer features to change the plotStyle JSON string stored in styleField
    :param layerID: QgsVectorLayer or vector id str
    :param styleField: str, name of string field in layer.fields() to store the PlotStyle
    :param id: feature id of feature for which the QgsAction was called
    """

    layer = findMapLayer(layerID)

    if isinstance(layer, QgsVectorLayer):
        selectedIDs = layer.selectedFeatureIds()
        if id in selectedIDs:
            ids = selectedIDs
        else:
            ids = [id]
        if len(ids) == 0:
            return

        wasEditable = layer.isEditable()
        if not wasEditable:
            if not layer.startEditing():
                raise Exception('Layer "{}" can not be edited'.format(layer.name()))
        layer.beginEditCommand('Remove {} features'.format(len(ids)))
        layer.deleteFeatures(ids)
        layer.endEditCommand()
        if not layer.commitChanges():
            errors = layer.commitErrors()
            raise Exception('Unable to save {} to layer {}'.format('\n'.join(errors), layer.name()))

        if wasEditable:
            layer.startEditing()

    else:
        raise Exception('unable to find layer "{}"'.format(layerID))


def createRemoveFeatureAction():
    """
    Creates a QgsAction to remove selected QgsFeatures from a QgsVectorLayer
    :return: QgsAction
    """

    iconPath = ':/images/themes/default/mActionDeleteSelected.svg'
    pythonCode = """
from {modulePath} import runRemoveFeatureActionRoutine
layerId = '[% @layer_id %]'
#layerId = [% "layer" %]
runRemoveFeatureActionRoutine(layerId, [% $id %])
""".format(modulePath=MODULE_IMPORT_PATH)

    return QgsAction(QgsAction.GenericPython, 'Remove Spectrum', pythonCode, iconPath, True,
                     notificationMessage='msgRemoveSpectra',
                     actionScopes={'Feature'})


def findTypeFromString(value: str):
    """
    Returns a fitting basic python data type of a string value, i.e.
    :param value: string
    :return: type out of [str, int or float]
    """
    for t in (int, float, str):
        try:
            _ = t(value)
        except ValueError:
            continue
        return t

    # every values can be converted into a string
    return str


def setComboboxValue(cb: QComboBox, text: str):
    """
    :param cb:
    :param text:
    :return:
    """
    assert isinstance(cb, QComboBox)
    currentIndex = cb.currentIndex()
    idx = -1
    if text is None:
        text = ''
    text = text.strip()
    for i in range(cb.count()):
        v = str(cb.itemText(i)).strip()
        if v == text:
            idx = i
            break
    if not idx >= 0:
        pass

    if idx >= 0:
        cb.setCurrentIndex(idx)
    else:
        log('ComboBox index not found for "{}"'.format(text))


def toType(t, arg, empty2None=True):
    """
    Converts lists or single values into type t.

    Examples:
        toType(int, '42') == 42,
        toType(float, ['23.42', '123.4']) == [23.42, 123.4]

    :param t: type
    :param arg: value to convert
    :param empty2None: returns None in case arg is an emptry value (None, '', NoneType, ...)
    :return: arg as type t (or None)
    """
    if isinstance(arg, list):
        return [toType(t, a) for a in arg]
    else:

        if empty2None and arg in EMPTY_VALUES:
            return None
        else:
            return t(arg)


def encodeProfileValueDict(d: dict, mode: SerializationMode = SerializationMode.PICKLE) -> str:
    """
    Converts a SpectralProfile value dictionary into a compact JSON string, which can be
    extracted with `decodeProfileValueDict`.
    :param d: dict
    :return: str
    """
    if not isinstance(d, dict):
        return None
    d2 = {}
    for k in EMPTY_PROFILE_VALUES.keys():
        v = d.get(k)
        # save keys with information only
        if v is not None:
            d2[k] = v
    if mode == SerializationMode.JSON:
        return json.dumps(d2, sort_keys=True, separators=(',', ':'))
    elif mode == SerializationMode.PICKLE:
        return QByteArray(pickle.dumps(d2))
    else:
        raise NotImplementedError()


def decodeProfileValueDict(dump, mode: SerializationMode = SerializationMode.PICKLE):
    """
    Converts a json / pickle dump  into a SpectralProfile value dictionary
    :param dump: str
    :return: dict
    """
    d = EMPTY_PROFILE_VALUES.copy()

    if dump not in EMPTY_VALUES:
        d2 = None
        if mode == SerializationMode.JSON:
            d2 = json.loads(dump)
        elif mode == SerializationMode.PICKLE:
            d2 = pickle.loads(dump)
        else:
            raise NotImplementedError()
        d.update(d2)
    return d


def qgsFieldAttributes2List(attributes) -> list:
    """Returns a list of attributes with None instead of NULL or QVariant.NULL"""
    r = QVariant(None)
    return [None if v == r else v for v in attributes]


def qgsFields2str(qgsFields: QgsFields) -> str:
    """Converts the QgsFields definition into a pickalbe string"""
    infos = []
    for field in qgsFields:
        assert isinstance(field, QgsField)
        info = [field.name(), field.type(), field.typeName(), field.length(), field.precision(), field.comment(),
                field.subType()]
        infos.append(info)
    return json.dumps(infos)


def str2QgsFields(fieldString: str) -> QgsFields:
    """Converts the string from qgsFields2str into a QgsFields collection"""
    fields = QgsFields()

    infos = json.loads(fieldString)
    assert isinstance(infos, list)
    for info in infos:
        field = QgsField(*info)
        fields.append(field)
    return fields


# Lookup table for ENVI IDL DataTypes to GDAL Data Types
LUT_IDL2GDAL = {1: gdal.GDT_Byte,
                12: gdal.GDT_UInt16,
                2: gdal.GDT_Int16,
                13: gdal.GDT_UInt32,
                3: gdal.GDT_Int32,
                4: gdal.GDT_Float32,
                5: gdal.GDT_Float64,
                #:gdal.GDT_CInt16,
                # 8:gdal.GDT_CInt32,
                6: gdal.GDT_CFloat32,
                9: gdal.GDT_CFloat64}


def ogrStandardFields() -> list:
    """Returns the minimum set of field a Spectral Library has to contain"""
    fields = [
        ogr.FieldDefn(FIELD_FID, ogr.OFTInteger),
        ogr.FieldDefn(FIELD_NAME, ogr.OFTString),
        ogr.FieldDefn('source', ogr.OFTString),
        ogr.FieldDefn(FIELD_VALUES, ogr.OFTString) \
            if SERIALIZATION == SerializationMode.JSON else \
            ogr.FieldDefn(FIELD_VALUES, ogr.OFTBinary),
    ]
    return fields


def createStandardFields():
    fields = QgsFields()
    for f in ogrStandardFields():
        assert isinstance(f, ogr.FieldDefn)
        name = f.GetName()
        ogrType = f.GetType()

        if ogrType == ogr.OFTString:
            a, b = QVariant.String, 'varchar'
        elif ogrType in [ogr.OFTInteger, ogr.OFTInteger64]:
            a, b = QVariant.Int, 'int'
        elif ogrType in [ogr.OFTReal]:
            a, b = QVariant.Double, 'double'
        elif ogrType in [ogr.OFTBinary]:
            a, b = QVariant.ByteArray, 'Binary'
        else:
            raise NotImplementedError()

        fields.append(QgsField(name, a, b))

    return fields


def value2str(value, sep: str = ' ') -> str:
    """
    Converst a value into a string
    :param value:
    :param sep: str separator for listed values
    :return:
    """
    if isinstance(value, list):
        value = sep.join([value2str(v, delimiter=sep) for v in value])
    elif isinstance(value, np.ndarray):
        value = value2str(value.astype(list), delimiter=sep)
    elif value in EMPTY_VALUES:
        value = ''
    else:
        value = str(value)
    return value


class SpectralProfile(QgsFeature):
    crs = SPECLIB_CRS

    @staticmethod
    def profileName(basename: str, pxPosition: QPoint = None, geoPosition: QgsPointXY = None, index: int = None):
        """
        Unified method to generate the name of a single profile
        :param basename: base name
        :param pxPosition: optional, pixel position in source image
        :param geoPosition: optional, pixel position in geo-coordinates
        :param index: index, e.g. n'th-1 profile that was sampled from a data set
        :return: name
        """

        name = basename

        if isinstance(index, int):
            name += str(index)

        if isinstance(pxPosition, QPoint):
            name += '({}:{})'.format(pxPosition.x(), pxPosition.y())
        elif isinstance(geoPosition, QgsPoint):
            name += '({}:{})'.format(geoPosition.x(), geoPosition.y())
        return name.replace(' ', ':')

    @staticmethod
    def fromMapCanvas(mapCanvas, position) -> list:
        """
        Returns a list of Spectral Profiles the raster layers in QgsMapCanvas mapCanvas.
        :param mapCanvas: QgsMapCanvas
        :param position: SpatialPoint
        """
        assert isinstance(mapCanvas, QgsMapCanvas)
        profiles = [SpectralProfile.fromRasterLayer(lyr, position) for lyr in mapCanvas.layers() if
                    isinstance(lyr, QgsRasterLayer)]
        return [p for p in profiles if isinstance(p, SpectralProfile)]

    @staticmethod
    def fromRasterSources(sources: list, position: SpatialPoint) -> list:
        """
        Returns a list of Spectral Profiles
        :param sources: list-of-raster-sources, e.g. file paths, gdal.Datasets, QgsRasterLayers
        :param position: SpatialPoint
        :return: [list-of-SpectralProfiles]
        """
        profiles = [SpectralProfile.fromRasterSource(s, position) for s in sources]
        return [p for p in profiles if isinstance(p, SpectralProfile)]

    @staticmethod
    def fromRasterLayer(layer: QgsRasterLayer, position: SpatialPoint):
        """
        Reads a SpectralProfile from a QgsRasterLayer
        :param layer: QgsRasterLayer
        :param position: SpatialPoint
        :return: SpectralProfile or None, if profile is out of layer bounds.
        """

        position = position.toCrs(layer.crs())
        if not layer.extent().contains(position):
            return None

        results = layer.dataProvider().identify(position, QgsRaster.IdentifyFormatValue).results()
        wl, wlu = parseWavelength(layer)

        y = list(results.values())
        y = [v if isinstance(v, (int, float)) else float('NaN') for v in y]

        profile = SpectralProfile()
        profile.setName(SpectralProfile.profileName(layer.name(), geoPosition=position))

        profile.setValues(x=wl, y=y, xUnit=wlu)

        profile.setCoordinates(position)
        profile.setSource('{}'.format(layer.source()))

        return profile

    @staticmethod
    def fromRasterSource(source, position, crs: QgsCoordinateReferenceSystem = None, gt: list = None,
                         fields: QgsFields = None):
        """
        Returns the Spectral Profiles from source at position `position`
        :param source: str | gdal.Dataset | QgsRasterLayer - the raster source
        :param position: list of positions
                        QPoint -> pixel index position
                        QgsPointXY -> pixel geolocation position in layer/raster CRS
                        SpatialPoint -> pixel geolocation position, will be transformed into layer/raster CRS
        :param crs: QgsCoordinateReferenceSystem - coordinate reference system of raster source, defaults to the raster source CRS
        :param gt: geo-transformation 6-tuple, defaults to the GT of the raster source
        :return: SpectralProfile with QgsPoint-Geometry in EPSG:43
        """

        if isinstance(source, str):
            ds = gdal.Open(source)
        elif isinstance(source, gdal.Dataset):
            ds = source
        elif isinstance(source, QgsRasterLayer):
            ds = gdal.Open(source.source())

        assert isinstance(ds, gdal.Dataset)

        file = ds.GetDescription()
        if os.path.isfile(file):
            baseName = os.path.basename(file)
        else:
            baseName = 'Spectrum'

        if not isinstance(crs, QgsCoordinateReferenceSystem):
            crs = QgsCoordinateReferenceSystem(ds.GetProjection())

        if not isinstance(gt, list):
            gt = ds.GetGeoTransform()

        geoCoordinate = None
        if isinstance(position, QPoint):
            px = position
            geoCoordinate = SpatialPoint(crs, px2geo(px, gt, pxCenter=True)).toCrs(SPECLIB_CRS)
        elif isinstance(position, SpatialPoint):
            px = geo2px(position.toCrs(crs), gt)
            geoCoordinate = position.toCrs(SPECLIB_CRS)
        elif isinstance(position, QgsPointXY):
            px = geo2px(position, ds.GetGeoTransform())
            geoCoordinate = SpatialPoint(crs, position).toCrs(SPECLIB_CRS)
        else:
            raise Exception('Unsupported type of argument "position" {}'.format('{}'.format(position)))

        # check out-of-raster
        if px.x() < 0 or px.y() < 0:
            return None
        if px.x() > ds.RasterXSize - 1 or px.y() > ds.RasterYSize - 1:
            return None

        y = ds.ReadAsArray(px.x(), px.y(), 1, 1)

        y = y.flatten()
        for b in range(ds.RasterCount):
            band = ds.GetRasterBand(b + 1)
            nodata = band.GetNoDataValue()
            if nodata and y[b] == nodata:
                return None

        wl, wlu = parseWavelength(ds)

        profile = SpectralProfile(fields=fields)
        profile.setName(SpectralProfile.profileName(baseName, pxPosition=px))
        profile.setValues(x=wl, y=y, xUnit=wlu)
        profile.setCoordinates(geoCoordinate)
        profile.setSource('{}'.format(ds.GetDescription()))
        return profile

    @staticmethod
    def fromSpecLibFeature(feature: QgsFeature):
        """
        Converts a QgsFeature into a SpectralProfile
        :param feature: QgsFeature
        :return: SpectralProfile
        """
        assert isinstance(feature, QgsFeature)
        sp = SpectralProfile(fields=feature.fields())
        sp.setId(feature.id())
        sp.setAttributes(feature.attributes())
        sp.setGeometry(feature.geometry())
        return sp

    def __init__(self, parent=None, fields=None, values: dict = None):

        if fields is None:
            fields = createStandardFields()
        assert isinstance(fields, QgsFields)
        # QgsFeature.__init__(self, fields)
        # QObject.__init__(self)
        super(SpectralProfile, self).__init__(fields)
        # QObject.__init__(self)
        # fields = self.fields()

        assert isinstance(fields, QgsFields)
        self.mValueCache = None
        # self.setStyle(DEFAULT_SPECTRUM_STYLE)
        if isinstance(values, dict):
            self.setValues(**values)

    def fieldNames(self) -> typing.List[str]:
        """
        Returns all field names
        :return:
        """
        return self.fields().names()

    def setName(self, name: str):
        if name != self.name():
            self.setAttribute(FIELD_NAME, name)
            # self.sigNameChanged.emit(name)

    def name(self) -> str:
        return self.metadata(FIELD_NAME)

    def setSource(self, uri: str):
        self.setAttribute('source', uri)

    def source(self):
        return self.metadata('source')

    def setCoordinates(self, pt):
        if isinstance(pt, SpatialPoint):
            sp = pt.toCrs(SpectralProfile.crs)
            self.setGeometry(QgsGeometry.fromPointXY(sp))
        elif isinstance(pt, QgsPointXY):
            self.setGeometry(QgsGeometry.fromPointXY(pt))

    def geoCoordinate(self):
        return self.geometry()

    def updateMetadata(self, metaData):
        if isinstance(metaData, dict):
            for key, value in metaData.items():
                self.setMetadata(key, value)

    def removeField(self, name):
        fields = self.fields()
        values = self.attributes()
        i = self.fieldNameIndex(name)
        if i >= 0:
            fields.remove(i)
            values.pop(i)
            self.setFields(fields)
            self.setAttributes(values)

    def setMetadata(self, key: str, value, addMissingFields=False):
        """
        :param key: Name of metadata field
        :param value: value to add. Need to be of type None, str, int or float.
        :param addMissingFields: Set on True to add missing fields (in case value is not None)
        :return:
        """
        i = self.fieldNameIndex(key)

        if i < 0:
            if value is not None and addMissingFields:
                fields = self.fields()
                values = self.attributes()
                fields.append(createQgsField(key, value))
                values.append(value)
                self.setFields(fields)
                self.setAttributes(values)

            return False
        else:
            return self.setAttribute(key, value)

    def metadata(self, key: str, default=None):
        """
        Returns a field value or None, if not existent
        :param key: str, field name
        :param default: default value to be returned
        :return: value
        """
        assert isinstance(key, str)
        i = self.fieldNameIndex(key)
        if i < 0:
            return None

        v = self.attribute(i)
        if v == QVariant(None):
            v = None
        return default if v is None else v

    def nb(self) -> int:
        """
        Returns the number of profile bands / profile values
        :return: int
        :rtype:
        """
        return len(self.yValues())

    def values(self) -> dict:
        """
        Returns a dictionary with 'x', 'y', 'xUnit' and 'yUnit' values.
        :return: {'x':list,'y':list,'xUnit':str,'yUnit':str, 'bbl':list}
        """
        if self.mValueCache is None:
            jsonStr = self.attribute(self.fields().indexFromName(FIELD_VALUES))
            d = decodeProfileValueDict(jsonStr)

            # save a reference to the decoded dictionary
            self.mValueCache = d

        return self.mValueCache

    def setValues(self, x=None, y=None, xUnit=None, yUnit=None, bbl=None):

        d = self.values().copy()

        if isinstance(x, np.ndarray):
            x = x.tolist()

        if isinstance(y, np.ndarray):
            y = y.tolist()

        if isinstance(bbl, np.ndarray):
            bbl = bbl.astype(bool).tolist()

        if isinstance(x, list):
            d['x'] = x

        if isinstance(y, list):
            d['y'] = y

        if isinstance(bbl, list):
            d['bbl'] = bbl

        # ensure x/y/bbl are list or None
        assert d['x'] is None or isinstance(d['x'], list)
        assert d['y'] is None or isinstance(d['y'], list)
        assert d['bbl'] is None or isinstance(d['bbl'], list)

        # ensure same length
        if isinstance(d['x'], list):
            assert isinstance(d['y'], list), 'y values need to be specified'

            assert len(d['x']) == len(d['y']), \
                'x and y need to have the same number of values ({} != {})'.format(len(d['x']), len(d['y']))

        if isinstance(d['bbl'], list):
            assert isinstance(d['y'], list), 'y values need to be specified'
            assert len(d['bbl']) == len(d['y']), \
                'y and bbl need to have the same number of values ({} != {})'.format(len(d['y']), len(d['bbl']))

        if isinstance(xUnit, str):
            d['xUnit'] = xUnit
        if isinstance(yUnit, str):
            d['yUnit'] = yUnit

        self.setAttribute(FIELD_VALUES, encodeProfileValueDict(d))
        self.mValueCache = d

    def xValues(self) -> list:
        """
        Returns the x Values / wavelength information.
        If wavelength information is not undefined it will return a list of band indices [0, ..., n-1]
        :return: [list-of-numbers]
        """
        x = self.values()['x']

        if not isinstance(x, list):
            return list(range(len(self.yValues())))
        else:
            return x

    def yValues(self) -> list:
        """
        Returns the x Values / DN / spectral profile values.
        List is empty if not numbers are stored
        :return: [list-of-numbers]
        """
        y = self.values()['y']
        if not isinstance(y, list):
            return []
        else:
            return y

    def bbl(self) -> list:
        """
        Returns the BadBandList.
        :return:
        :rtype:
        """
        bbl = self.values().get('bbl')
        if not isinstance(bbl, list):
            bbl = np.ones(self.nb(), dtype=np.byte).tolist()
        return bbl

    def setXUnit(self, unit: str):
        d = self.values()
        d['xUnit'] = unit
        self.setValues(**d)

    def xUnit(self) -> str:
        """
        Returns the semantic unit of x values, e.g. a wavelength unit like 'nm' or 'um'
        :return: str
        """
        return self.values()['xUnit']

    def setYUnit(self, unit: str = None):
        """
        :param unit:
        :return:
        """
        d = self.values()
        d['yUnit'] = unit
        self.setValues(**d)

    def yUnit(self) -> str:
        """
        Returns the semantic unit of y values, e.g. 'reflectances'"
        :return: str
        """

        return self.values()['yUnit']

    def copyFieldSubset(self, fields):

        sp = SpectralProfile(fields=fields)

        fieldsInCommon = [field for field in sp.fields() if field in self.fields()]

        sp.setGeometry(self.geometry())
        sp.setId(self.id())

        for field in fieldsInCommon:
            assert isinstance(field, QgsField)
            i = sp.fieldNameIndex(field.name())
            sp.setAttribute(i, self.attribute(field.name()))
        return sp

    def clone(self):
        """
        Create a clone of this SpectralProfile
        :return: SpectralProfile
        """
        return self.__copy__()

    def plot(self) -> QWidget:
        """
        Plots this profile to an new PyQtGraph window
        :return:
        """
        from .gui import SpectralProfilePlotDataItem
        from ..plotstyling.plotstyling import PlotStyle
        from ..externals import pyqtgraph as pg
        pdi = SpectralProfilePlotDataItem(self)
        pdi.setClickable(True)
        pw = pg.plot(title=self.name())
        pw.getPlotItem().addItem(pdi)

        style = PlotStyle.fromPlotDataItem(pdi)
        style.setLineColor('green')
        style.setMarkerSymbol('Triangle')
        style.setMarkerColor('green')
        style.apply(pdi)

        return pw
        # pg.QAPP.exec_()

    def __reduce_ex__(self, protocol):

        return self.__class__, (), self.__getstate__()

    def __getstate__(self):

        if self.mValueCache is None:
            self.values()
        wkt = self.geometry().asWkt()
        state = (qgsFields2str(self.fields()), qgsFieldAttributes2List(self.attributes()), wkt)
        dump = pickle.dumps(state)
        return dump

    def __setstate__(self, state):
        state = pickle.loads(state)
        fields, attributes, wkt = state
        fields = str2QgsFields(fields)
        self.setFields(fields)
        self.setGeometry(QgsGeometry.fromWkt(wkt))
        self.setAttributes(attributes)

    def __copy__(self):
        sp = SpectralProfile(fields=self.fields())
        sp.setId(self.id())
        sp.setAttributes(self.attributes())
        sp.setGeometry(QgsGeometry.fromWkt(self.geometry().asWkt()))
        if isinstance(self.mValueCache, dict):
            sp.values()
        return sp

    def __eq__(self, other):
        if not isinstance(other, SpectralProfile):
            return False
        if not np.array_equal(self.fieldNames(), other.fieldNames()):
            return False

        names1 = self.fieldNames()
        names2 = other.fieldNames()
        for i1, n in enumerate(self.fieldNames()):
            if n == FIELD_FID:
                continue
            elif n == FIELD_VALUES:
                if self.xValues() != other.xValues():
                    return False
                if self.yValues() != other.yValues():
                    return False
                if self.xUnit() != other.xUnit():
                    return False
            else:
                i2 = names2.index(n)
                if self.attribute(i1) != other.attribute(i2):
                    return False

        return True

    def __hash__(self):

        return hash(id(self))

    def setId(self, id):
        self.setAttribute(FIELD_FID, id)
        if id is not None:
            super(SpectralProfile, self).setId(id)

    """
    def __eq__(self, other):
        if not isinstance(other, SpectralProfile):
            return False
        if len(self.mValues) != len(other.mValues):
            return False
        return all(a == b for a,b in zip(self.mValues, other.mValues)) \
            and self.mValuePositions == other.mValuePositions \
            and self.mValueUnit == other.mValueUnit \
            and self.mValuePositionUnit == other.mValuePositionUnit \
            and self.mGeoCoordinate == other.mGeoCoordinate \
            and self.mPxCoordinate == other.mPxCoordinate

    def __ne__(self, other):
        return not self.__eq__(other)
    """

    def __len__(self):
        return len(self.yValues())


def defaultCurvePlotStyle() -> PlotStyle:
    ps = PlotStyle()
    ps.setLineColor('white')
    ps.markerSymbol = None
    ps.linePen.setStyle(Qt.SolidLine)
    return ps


class SpectralProfileRenderer(object):

    @staticmethod
    def default():
        """
        Returns the default plotStyle scheme.
        :return:
        :rtype: SpectralProfileRenderer
        """
        return SpectralProfileRenderer.dark()

    @staticmethod
    def fromUserSettings():
        """
        Returns the SpectralProfileRenderer last  saved in then library settings
        :return:
        :rtype:
        """
        settings = speclibSettings()

        scheme = SpectralProfileRenderer.default()

        if SpectralLibrarySettingsKey.DEFAULT_PROFILE_STYLE.name in settings.allKeys():
            scheme.profileStyle = PlotStyle.fromJSON(
                settings.value(SpectralLibrarySettingsKey.DEFAULT_PROFILE_STYLE.name))
        if SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE.name in settings.allKeys():
            scheme.temporaryProfileStyle = PlotStyle.fromJSON(
                settings.value(SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE.name))

        scheme.backgroundColor = settings.value(SpectralLibrarySettingsKey.BACKGROUND_COLOR.name,
                                                scheme.backgroundColor)
        scheme.foregroundColor = settings.value(SpectralLibrarySettingsKey.FOREGROUND_COLOR.name,
                                                scheme.foregroundColor)
        scheme.infoColor = settings.value(SpectralLibrarySettingsKey.INFO_COLOR.name, scheme.infoColor)
        scheme.selectionColor = settings.value(SpectralLibrarySettingsKey.SELECTION_COLOR.name, scheme.selectionColor)
        scheme.useRendererColors = settings.value(SpectralLibrarySettingsKey.USE_VECTOR_RENDER_COLORS.name,
                                                  scheme.useRendererColors) in ['True', 'true', True]

        return scheme

    @staticmethod
    def dark():
        ps = defaultCurvePlotStyle()
        ps.setLineColor('white')

        cs = defaultCurvePlotStyle()
        cs.setLineColor('green')

        return SpectralProfileRenderer(
            name='Dark',
            fg=QColor('white'),
            bg=QColor('black'),
            ic=QColor('yellow'),
            sc=QColor('yellow'),
            ps=ps, cs=cs, useRendererColors=False)

    @staticmethod
    def bright():
        ps = defaultCurvePlotStyle()
        ps.setLineColor('black')

        cs = defaultCurvePlotStyle()
        cs.setLineColor('green')

        return SpectralProfileRenderer(
            name='Bright',
            fg=QColor('black'),
            bg=QColor('white'),
            ic=QColor('red'),
            sc=QColor('red'),
            ps=ps, cs=cs, useRendererColors=False)

    def __init__(self,
                 name: str = 'color_scheme',
                 fg: QColor = QColor('white'),
                 bg: QColor = QColor('black'),
                 ps: PlotStyle = None,
                 cs: PlotStyle = None,
                 ic: QColor = QColor('yellow'),
                 sc: QColor = QColor('yellow'),
                 useRendererColors: bool = True):
        """
        :param name: name of color scheme
        :type name: str
        :param fg: foreground color
        :type fg: QColor
        :param bg: background color
        :type bg: QColor
        :param ps: default profile style
        :type ps: PlotStyle
        :param cs: current profile style, i.e. selected profiles
        :type cs: PlotStyle
        :param ic: info color, color of additional information, like crosshair and cursor location
        :type ic: QColor
        :param useRendererColors: if true (default), use colors from the QgsVectorRenderer to colorize plot lines
        :type useRendererColors: bool
        """

        if ps is None:
            ps = defaultCurvePlotStyle()

        if cs is None:
            cs = defaultCurvePlotStyle()
            cs.setLineColor('green')

        self.name: str
        self.name = name

        self.foregroundColor: QColor
        self.foregroundColor = fg

        self.backgroundColor: QColor
        self.backgroundColor = bg

        self.profileStyle: PlotStyle
        self.profileStyle = ps

        self.temporaryProfileStyle: PlotStyle
        self.temporaryProfileStyle = cs

        self.infoColor: QColor
        self.infoColor = ic

        self.selectionColor: QColor
        self.selectionColor = sc
        self.useRendererColors: bool
        self.useRendererColors = useRendererColors

        self.mFID2Style: dict = dict()
        self.mTemporaryFIDs: set = set()
        self.mInputSource: QgsVectorLayer = None

    def reset(self):
        self.mFID2Style.clear()

    @staticmethod
    def readXml(node: QDomElement, *args):
        """
        Reads the PlotStyle from a QDomElement (XML node)
        :param self:
        :param node:
        :param args:
        :return:
        """
        from .core import XMLNODE_PROFILE_RENDERER
        if node.tagName() != XMLNODE_PROFILE_RENDERER:
            node = node.firstChildElement(XMLNODE_PROFILE_RENDERER)
        if node.isNull():
            return None

        renderer = SpectralProfileRenderer()
        renderer.backgroundColor = QColor(node.attribute('bg', renderer.backgroundColor.name()))
        renderer.foregroundColor = QColor(node.attribute('fg', renderer.foregroundColor.name()))
        renderer.selectionColor = QColor(node.attribute('sc', renderer.selectionColor.name()))
        renderer.infoColor = QColor(node.attribute('ic', renderer.infoColor.name()))
        renderer.useRendererColors = 'true' == node.attribute('use_symbolcolor',
                                                              str(renderer.useRendererColors)).lower()

        nodeName = node.firstChildElement('name')
        renderer.name = nodeName.firstChild().nodeValue()

        nodeDefaultStyle = node.firstChildElement('default_style')
        renderer.profileStyle = PlotStyle.readXml(nodeDefaultStyle)

        customStyleNodes = node.firstChildElement('custom_styles').childNodes()
        for i in range(customStyleNodes.count()):
            customStyleNode = customStyleNodes.at(i)
            customStyle = PlotStyle.readXml(customStyleNode)
            if isinstance(customStyle, PlotStyle):
                fids = customStyleNode.firstChildElement('fids').firstChild().nodeValue().split(',')
                fids = [int(f) for f in fids]
                renderer.setProfilePlotStyle(customStyle, fids)

        return renderer

    def setInput(self, vectorLayer: QgsVectorLayer):
        self.mInputSource = vectorLayer

    def writeXml(self, node: QDomElement, doc: QDomDocument) -> bool:
        """
        Writes the PlotStyle to a QDomNode
        :param node:
        :param doc:
        :return:
        """
        from .core import XMLNODE_PROFILE_RENDERER
        profileRendererNode = doc.createElement(XMLNODE_PROFILE_RENDERER)
        profileRendererNode.setAttribute('bg', self.backgroundColor.name())
        profileRendererNode.setAttribute('fg', self.foregroundColor.name())
        profileRendererNode.setAttribute('sc', self.selectionColor.name())
        profileRendererNode.setAttribute('ic', self.infoColor.name())
        profileRendererNode.setAttribute('use_symbolcolor', str(self.useRendererColors))

        nodeName = doc.createElement('name')
        nodeName.appendChild(doc.createTextNode(self.name))
        profileRendererNode.appendChild(nodeName)

        nodeDefaultStyle = doc.createElement('default_style')
        self.profileStyle.writeXml(nodeDefaultStyle, doc)
        profileRendererNode.appendChild(nodeDefaultStyle)

        nodeCustomStyles = doc.createElement('custom_styles')

        customStyles = self.nonDefaultPlotStyles()
        for style in customStyles:
            fids = [k for k, s in self.mFID2Style.items() if s == style]
            nodeStyle = doc.createElement('custom_style')
            style.writeXml(nodeStyle, doc)
            nodeFIDs = doc.createElement('fids')
            nodeFIDs.appendChild(doc.createTextNode(','.join([str(i) for i in fids])))
            nodeStyle.appendChild(nodeFIDs)
            nodeCustomStyles.appendChild(nodeStyle)
        profileRendererNode.appendChild(nodeCustomStyles)
        node.appendChild(profileRendererNode)

        return True

    def setTemporaryFIDs(self, fids):
        self.mTemporaryFIDs.clear()
        self.mTemporaryFIDs.update(fids)

    def setProfilePlotStyle(self, plotStyle, fids: typing.List[int]) -> typing.List[int]:
        if isinstance(fids, int):
            fids = [fids]
        changedFIDs = [f for f in fids if self.mFID2Style.get(f) != plotStyle]

        if isinstance(plotStyle, PlotStyle):
            for fid in fids:
                self.mFID2Style[fid] = plotStyle
        else:
            # use default style
            for fid in fids:
                self.mFID2Style.pop(fid)

        return changedFIDs

    def nonDefaultPlotStyles(self) -> typing.List[PlotStyle]:
        return list(set(self.mFID2Style.values()))

    def profilePlotStyles(self, fids: typing.List[int]) -> typing.Dict[int, PlotStyle]:

        profileStyles: typing.Dict[int, PlotStyle] = dict()

        if isinstance(self.mInputSource, QgsVectorLayer):
            selectedFIDs = self.mInputSource.selectedFeatureIds()
        else:
            selectedFIDs = []

        if self.useRendererColors and isinstance(self.mInputSource, QgsVectorLayer):
            renderContext = QgsRenderContext()
            renderContext.setExtent(self.mInputSource.extent())
            renderer = self.mInputSource.renderer().clone()
            renderer.setInput(self.mInputSource.dataSource())
            renderer.startRender(renderContext, self.mInputSource.fields())
            features = self.mInputSource.getFeatures(fids)

            for i, feature in enumerate(features):
                fid = feature.fid
                style = self.mFID2Style.get(fid, self.mDefaultPlotStyle).clone()
                symbol = renderer.symbolForFeature(feature, renderContext)
                if not isinstance(symbol, QgsSymbol):
                    symbol = renderer.sourceSymbol()
                assert isinstance(symbol, QgsSymbol)
                if isinstance(symbol, (QgsMarkerSymbol, QgsLineSymbol, QgsFillSymbol)):
                    style.setLineColor(symbol.color())
                    style.setMarkerColor(symbol.color())
                profileStyles[fid] = style
            renderer.stopRender(renderContext)
        else:
            for fid in fids:
                if fid not in self.mFID2Style.keys():
                    s = ""
                profileStyles[fid] = self.mFID2Style.get(fid, self.profileStyle).clone()

        line_increase_selected = 2
        line_increase_temp = 3

        # highlight selected features
        for fid, style in profileStyles.items():
            if fid in selectedFIDs:
                style.setLineColor(self.selectionColor)
                style.setMarkerColor(self.selectionColor)
                style.markerBrush.setColor(self.selectionColor)
                style.markerSize += line_increase_selected
                style.linePen.setWidth(style.linePen.width() + line_increase_selected)
            elif fid in self.mTemporaryFIDs:
                style.markerSize += line_increase_selected
                style.linePen.setWidth(style.linePen.width() + line_increase_selected)

        return profileStyles

    def clone(self):
        return copy.deepcopy(self)

    def __copy__(self):
        return copy.copy(self)

    def saveToUserSettings(self):
        """
        Saves this plotStyle scheme to the user Qt user settings
        :return:
        :rtype:
        """
        settings = speclibSettings()

        settings.setValue(SpectralLibrarySettingsKey.DEFAULT_PROFILE_STYLE.name, self.profileStyle.json())
        settings.setValue(SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE.name, self.temporaryProfileStyle.json())
        settings.setValue(SpectralLibrarySettingsKey.BACKGROUND_COLOR.name, self.backgroundColor)
        settings.setValue(SpectralLibrarySettingsKey.FOREGROUND_COLOR.name, self.foregroundColor)
        settings.setValue(SpectralLibrarySettingsKey.INFO_COLOR.name, self.infoColor)
        settings.setValue(SpectralLibrarySettingsKey.SELECTION_COLOR.name, self.selectionColor)
        settings.setValue(SpectralLibrarySettingsKey.USE_VECTOR_RENDER_COLORS.name, self.useRendererColors)

    def __eq__(self, other):
        if not isinstance(other, SpectralProfileRenderer):
            return False
        else:
            keys = [k for k in self.__dict__.keys()
                    if not k.startswith('_') and
                    k not in ['name']]

            for k in keys:
                if self.__dict__[k] != other.__dict__[k]:
                    return False
            return True


class SpectralLibrary(QgsVectorLayer):
    """
    SpectralLibrary
    """

    @staticmethod
    def readFromMimeData(mimeData: QMimeData):
        """
        Reads a SpectraLibrary from mime data.
        :param mimeData: QMimeData
        :return: SpectralLibrary
        """
        if MIMEDATA_SPECLIB_LINK in mimeData.formats():
            # extract from link
            sid = pickle.loads(mimeData.data(MIMEDATA_SPECLIB_LINK))
            global SPECLIB_CLIPBOARD
            sl = SPECLIB_CLIPBOARD.get(sid)
            if isinstance(sl, SpectralLibrary) and id(sl) == sid:
                return sl

        if MIMEDATA_SPECLIB in mimeData.formats():
            sl = SpectralLibrary.readFromPickleDump(mimeData.data(MIMEDATA_SPECLIB))
            if isinstance(sl, SpectralLibrary) and len(sl) > 0:
                return sl

        if mimeData.hasUrls():
            urls = mimeData.urls()
            if isinstance(urls, list) and len(urls) > 0:
                sl = SpectralLibrary.readFrom(urls[0])
                if isinstance(sl, SpectralLibrary) and len(sl) > 0:
                    return sl

        if MIMEDATA_TEXT in mimeData.formats():
            txt = mimeData.text()
            from ..speclib.io.csvdata import CSVSpectralLibraryIO
            sl = CSVSpectralLibraryIO.fromString(txt)
            if isinstance(sl, SpectralLibrary) and len(sl) > 0:
                return sl

        return None

    @staticmethod
    def readFromPickleDump(data):
        """
        Reads a SpectralLibrary from a pickle.dump()-generate bytes object.
        :param data: bytes
        :return: SpectralLibrary
        """
        return pickle.loads(data)

    @staticmethod
    def readFromSourceDialog(parent=None):
        """
        Opens a FileOpen dialog to select a spectral library
        :param parent:
        :return: SpectralLibrary
        """

        SETTINGS = speclibSettings()
        lastDataSourceDir = SETTINGS.value('SpeclibSourceDirectory', '')

        if not QFileInfo(lastDataSourceDir).isDir():
            lastDataSourceDir = None

        uris, filter = QFileDialog.getOpenFileNames(parent, "Open spectral library", lastDataSourceDir,
                                                    filter=FILTERS + ';;All files (*.*)', )

        if len(uris) > 0:
            SETTINGS.setValue('SpeclibSourceDirectory', os.path.dirname(uris[0]))

        uris = [u for u in uris if QFileInfo(u).isFile()]

        if len(uris) == 0:
            return None

        speclib = SpectralLibrary()
        speclib.startEditing()
        for u in uris:
            sl = SpectralLibrary.readFrom(str(u))
            if isinstance(sl, SpectralLibrary):
                speclib.addProfiles(sl)
        assert speclib.commitChanges()
        return speclib

    # thanks to Ann for providing https://bitbucket.org/jakimowb/qgispluginsupport/issues/6/speclib-spectrallibrariespy
    @staticmethod
    def readFromVector(vector: QgsVectorLayer = None,
                       raster: QgsRasterLayer = None,
                       progress_handler: typing.Union[QProgressDialog, ProgressHandler] = None,
                       name_field: str = None,
                       all_touched: bool = False,
                       cache: int = 5*2**20,
                       copy_attributes: bool = False,
                       block_size: typing.Tuple[int, int] = None,
                       return_profile_list: bool = False):
        """
        Reads SpectraProfiles from a raster source, based on the locations specified in a vector data set.
        Opens a Select Polygon Layer dialog to select the correct polygon and returns a Spectral Library with
        metadata according to the polygons attribute table.

        :param block_size:
        :param copy_attributes:
        :param cache:
        :param vector: QgsVectorLayer | str
        :param raster: QgsRasterLayer | str
        :param progress_handler: QProgressDialog (optional)
        :param name_field: str | int | QgsField that is used to generate individual profile names.
        :param all_touched: bool, False (default) = extract only pixel entirely covered with a geometry
                                  True = extract all pixels touched by a geometry
        :param return_profile_list: bool, False (default) = return a SpectralLibrary
                                        True = return a [list-of-SpectralProfiles] and skip the creation of
                                        a SpectralLibrary. This might become faster if the spectral profiles
                                        are to be added to another SpectraLibrary anyway.
        :return: Spectral Library | [list-of-profiles]
        """

        t0 = datetime.datetime.now()
        dtReport = datetime.timedelta(seconds=1)

        # get QgsLayers of vector and raster
        if vector is None and raster is None:
            from ..utils import SelectMapLayersDialog
            dialog = SelectMapLayersDialog()
            dialog.addLayerDescription('Raster', QgsMapLayerProxyModel.RasterLayer)
            dialog.addLayerDescription('Vector', QgsMapLayerProxyModel.VectorLayer)
            dialog.exec_()
            if dialog.result() == QDialog.Accepted:
                raster, vector = dialog.mapLayers()

                if not isinstance(vector, QgsVectorLayer) or not isinstance(raster, QgsRasterLayer):
                    return

        vector: QgsVectorLayer = qgsVectorLayer(vector)
        raster: QgsRasterLayer = qgsRasterLayer(raster)

        if name_field:
            assert name_field in vector.fields().names(), \
                f'invalid field name "{name_field}". Allowed values are {", ".join(vector.fields().names())}'
        else:
            for i in range(vector.fields().count()):
                field:QgsField = vector.fields().at(i)
                if field.type() == QVariant.String and re.search('name', field.name(), re.I):
                    name_field = field.name()
                    break

        ds: gdal.Dataset = gdalDataset(raster)
        assert isinstance(ds, gdal.Dataset), f'Unable to open {raster.source()} as gdal.Dataset'

        if progress_handler:
            progress_handler.setLabelText('Calculate profile positions...')

        bbl = parseBadBandList(ds)
        wl, wlu = parseWavelength(ds)

        # the SpectralLibrary to be returned
        spectral_library = SpectralLibrary()
        spectral_library.startEditing()

        # add other attributes to SpectralLibrary
        fields_to_copy = []
        if copy_attributes:
            for field in vector.fields():
                assert isinstance(field, QgsField)
                if field.name() not in spectral_library.fields().names():
                    spectral_library.addAttribute(QgsField(field))
                    fields_to_copy.append(field.name())
        assert spectral_library.commitChanges()
        assert spectral_library.startEditing()

        if block_size is None:
            block_size = optimize_block_size(ds, cache=cache)

        nXBlocks = int((ds.RasterXSize + block_size[0] - 1) / block_size[0])
        nYBlocks = int((ds.RasterYSize + block_size[1] - 1) / block_size[1])
        nBlocksTotal = nXBlocks * nYBlocks
        nBlocksDone = 0

        if progress_handler:
            progress_handler.setRange(0, nBlocksTotal+1)

        # pixel center coordinates as geolocation
        geo_x, geo_y = px2geocoordinates(ds,
                                         target_srs=spectral_library.crs(),
                                         pxCenter=True)

        # get FID positions
        layer = 0
        for sub in vector.dataProvider().subLayers():
            layer = sub.split('!!::!!')[1]
            break

        fid_positions, no_fid = fid2pixelindices(ds, vector,
                                                 layer=layer,
                                                 all_touched=all_touched)

        if progress_handler:
            progress_handler.setLabelText('Read profile values..')
            progress_handler.setValue(progress_handler.value()+1)


        PROFILE_COUNTS = dict()

        FEATURES: typing.Dict[int, QgsFeature] = dict()


        block_profiles = []

        for y in range(nYBlocks):
            yoff = y * block_size[1]
            for x in range(nXBlocks):
                xoff = x * block_size[0]
                xsize = min(block_size[0], ds.RasterXSize - xoff)
                ysize = min(block_size[1], ds.RasterYSize - yoff)
                cube: np.ndarray = ds.ReadAsArray(xoff=xoff, yoff=yoff, xsize=xsize, ysize=ysize)
                fid_pos = fid_positions[yoff:yoff + ysize, xoff:xoff + xsize]
                assert cube.shape[1:] == fid_pos.shape

                for fid in [int(v) for v in np.unique(fid_pos) if v != no_fid]:
                    fid_yy, fid_xx = np.where(fid_pos == fid)
                    n_p = len(fid_yy)
                    if n_p > 0:

                        if fid not in FEATURES.keys():
                            FEATURES[fid] = vector.getFeature(fid)
                        vectorFeature: QgsFeature = FEATURES.get(fid)
                        if name_field:
                            fid_basename = str(FEATURES[fid].attribute(name_field)).strip()
                        else:
                            fid_basename = f'{vector.name()} {fid}'.strip()

                        fid_profiles = cube[:, fid_yy, fid_xx]
                        profile_geo_x = geo_x[fid_yy + yoff, fid_xx + xoff]
                        profile_geo_y = geo_y[fid_yy + yoff, fid_xx + xoff]

                        for i in range(n_p):
                            # create profile feature
                            sp = SpectralProfile(fields=spectral_library.fields())

                            # create geometry
                            sp.setGeometry(QgsPoint(profile_geo_x[i],
                                                    profile_geo_y[i]))

                            PROFILE_COUNTS[fid] = PROFILE_COUNTS.get(fid, 0) + 1
                            sp.setName(f'{fid_basename}_{PROFILE_COUNTS[fid]}')
                            sp.setValues(x=wl,
                                         y=fid_profiles[:, i],
                                         xUnit=wlu,
                                         bbl=bbl)
                            if vectorFeature.isValid():
                                for field_name in fields_to_copy:
                                    sp[field_name] = vectorFeature[field_name]
                            if progress_handler and progress_handler.wasCanceled():
                                return None

                            block_profiles.append(sp)
                if not return_profile_list:
                    if not spectral_library.addFeatures(block_profiles):
                        spectral_library.raiseError()
                    block_profiles.clear()

                nBlocksDone += 1
                if progress_handler:
                    if nBlocksDone == nBlocksTotal or datetime.datetime.now() - t0 > dtReport:
                        t0 = datetime.datetime.now()
                        progress_handler.setValue(nBlocksDone + 1)

        if return_profile_list:
            return block_profiles
        else:
            if not spectral_library.commitChanges():
                spectral_library.raiseError()

            return spectral_library

    @staticmethod
    def readFromVectorPositions(rasterSource, vectorSource, mode='CENTROIDS', \
                                progressDialog: typing.Union[QProgressDialog, ProgressHandler] = None):
        """

        :param pathRaster:
        :param vectorSource:
        :param mode:
        :return:
        """
        warnings.warn(DeprecationWarning(r'Use readFromVector instead'))
        assert mode in ['CENTROIDS', 'AVERAGES', 'PIXELS']

        if isinstance(rasterSource, str):
            rasterSource = QgsRasterLayer(rasterSource)
        elif isinstance(rasterSource, gdal.Dataset):
            rasterSource = QgsRasterLayer(rasterSource, '', 'gdal')

        assert isinstance(rasterSource, QgsRasterLayer)

        if isinstance(vectorSource, str):
            vectorSource = QgsVectorLayer(vectorSource)
        elif isinstance(vectorSource, ogr.DataSource):
            raise NotImplementedError()

        assert isinstance(vectorSource, QgsVectorLayer)

        extentRaster = SpatialExtent.fromLayer(rasterSource)
        vectorSource.selectByRect(extentRaster.toCrs(vectorSource.crs()))

        trans = QgsCoordinateTransform()
        trans.setSourceCrs(vectorSource.crs())
        trans.setDestinationCrs(rasterSource.crs())

        nSelected = vectorSource.selectedFeatureCount()

        gt = layerGeoTransform(rasterSource)
        extent = rasterSource.extent()
        center = extent.center()
        # m2p = QgsMapToPixel(rasterSource.rasterUnitsPerPixelX(),
        #                    center.x() + 0.5*rasterSource.rasterUnitsPerPixelX(),
        #                    center.y() - 0.5*rasterSource.rasterUnitsPerPixelY(),
        #                    rasterSource.width(), rasterSource.height(), 0)

        pixelpositions = []

        if isinstance(progressDialog, (QProgressDialog, ProgressHandler)):
            progressDialog.setMinimum(0)
            progressDialog.setMaximum(nSelected)
            progressDialog.setLabelText('Get pixel positions...')

        nMissingGeometry = []
        for i, feature in enumerate(vectorSource.selectedFeatures()):
            if isinstance(progressDialog, (QProgressDialog, ProgressHandler)) and progressDialog.wasCanceled():
                return None

            assert isinstance(feature, QgsFeature)

            if feature.hasGeometry():
                g = feature.geometry().constGet()

                if isinstance(g, QgsPoint):
                    point = trans.transform(QgsPointXY(g))
                    px = geo2px(point, gt)
                    pixelpositions.append(px)

                if isinstance(g, QgsMultiPoint):
                    for point in g.parts():
                        if isinstance(point, QgsPoint):
                            point = trans.transform(QgsPointXY(point))
                            px = geo2px(point, gt)
                            pixelpositions.append(px)
                    s = ""
            else:
                nMissingGeometry += 1

            if isinstance(progressDialog, (QProgressDialog, ProgressHandler)):
                progressDialog.setValue(progressDialog.value() + 1)

        if len(nMissingGeometry) > 0:
            print('{} features without geometry in {}'.format(nMissingGeometry))

        return SpectralLibrary.readFromRasterPositions(rasterSource, pixelpositions, progressDialog=progressDialog)

    def reloadSpectralValues(self, raster, selectedOnly: bool = True):
        """
        Reloads the spectral values for each point based on the spectral values found in raster image "raster"
        :param raster: str | QgsRasterLayer | gdal.Dataset
        :param selectedOnly: bool, if True (default) spectral values will be retireved for selected features only.
        """
        assert self.isEditable()

        source = gdalDataset(raster)
        assert isinstance(source, gdal.Dataset)
        gt = source.GetGeoTransform()
        crs = QgsCoordinateReferenceSystem(source.GetProjection())

        geoPositions = []
        fids = []

        features = self.selectedFeatures() if selectedOnly else self.features()
        for f in features:
            assert isinstance(f, QgsFeature)
            if f.hasGeometry():
                fids.append(f.id())
                geoPositions.append(QgsPointXY(f.geometry().get()))
        if len(fids) == 0:
            return

        # transform feature coordinates into the raster data set's CRS
        if crs != self.crs():
            trans = QgsCoordinateTransform()
            trans.setSourceCrs(self.crs())
            trans.setDestinationCrs(crs)
            geoPositions = [trans.transform(p) for p in geoPositions]

        # transform coordinates into pixel positions
        pxPositions = [geo2px(p, gt) for p in geoPositions]

        idxSPECLIB = self.fields().indexOf(FIELD_VALUES)
        idxPROFILE = None

        for fid, pxPosition in zip(fids, pxPositions):
            assert isinstance(pxPosition, QPoint)
            profile = SpectralProfile.fromRasterSource(source, pxPosition, crs=crs, gt=gt)
            if isinstance(profile, SpectralProfile):
                if idxPROFILE is None:
                    idxPROFILE = profile.fields().indexOf(FIELD_VALUES)
                assert self.changeAttributeValue(fid, idxSPECLIB, profile.attribute(idxPROFILE))

    @staticmethod
    def readFromRasterPositions(pathRaster, positions,
                                progressDialog: typing.Union[QProgressDialog, ProgressHandler] = None):
        """
        Reads a SpectralLibrary from a set of positions
        :param pathRaster:
        :param positions:
        :return:
        """
        if not isinstance(positions, list):
            positions = [positions]
        profiles = []

        source = gdalDataset(pathRaster)
        i = 0

        nTotal = len(positions)
        if isinstance(progressDialog, (QProgressDialog, ProgressHandler)):
            progressDialog.setMinimum(0)
            progressDialog.setMaximum(nTotal)
            progressDialog.setValue(0)
            progressDialog.setLabelText('Extract pixel profiles...')

        for p, position in enumerate(positions):

            if isinstance(progressDialog, (QProgressDialog, ProgressHandler)) and progressDialog.wasCanceled():
                return None

            profile = SpectralProfile.fromRasterSource(source, position)
            if isinstance(profile, SpectralProfile):
                profiles.append(profile)
                i += 1

            if isinstance(progressDialog, (QProgressDialog, ProgressHandler)):
                progressDialog.setValue(progressDialog.value() + 1)

        sl = SpectralLibrary()
        sl.startEditing()
        sl.addProfiles(profiles)
        assert sl.commitChanges()
        return sl

    def readJSONProperties(self, pathJSON: str):
        """
        Reads additional SpectralLibrary properties from a JSON definition according to
        https://enmap-box.readthedocs.io/en/latest/usr_section/usr_manual/processing_datatypes.html#labelled-spectral-library

        :param pathJSON: file path (any) | JSON dictionary | str

        :returns: None | JSON dictionary
        """
        jsonData = None
        try:
            if isinstance(pathJSON, dict):
                jsonData = pathJSON
            elif isinstance(pathJSON, str):
                if os.path.isfile(pathJSON):
                    if not re.search(r'.json$', pathJSON):
                        pathJSON = os.path.splitext(pathJSON)[0] + '.json'
                        if not os.path.isfile(pathJSON):
                            return
                    with open(pathJSON, 'r') as file:
                        jsonData = json.load(file)
                else:
                    jsonData = json.loads(pathJSON)

        except Exception as ex:
            print(ex, file=sys.stderr)
            pass

        if not isinstance(jsonData, dict):
            return None
        b = self.isEditable()
        self.startEditing()
        try:
            for fieldName in self.fields().names():
                fieldIndex = self.fields().lookupField(fieldName)
                field = self.fields().at(fieldIndex)
                assert isinstance(field, QgsField)
                assert isinstance(fieldName, str)
                if fieldName in jsonData.keys():
                    fieldProperties = jsonData[fieldName]
                    assert isinstance(fieldProperties, dict)

                    # see https://enmap-box.readthedocs.io/en/latest/usr_section/usr_manual/processing_datatypes.html#labelled-spectral-library
                    # for details
                    if 'categories' in fieldProperties.keys():
                        from ..classification.classificationscheme import ClassificationScheme, ClassInfo, \
                            classSchemeToConfig
                        from ..classification.classificationscheme import EDITOR_WIDGET_REGISTRY_KEY as ClassEditorKey
                        classes = []
                        for item in fieldProperties['categories']:
                            cColor = None
                            if len(item) >= 3:
                                cColor = item[2]
                                if isinstance(cColor, str):
                                    cColor = QColor(cColor)
                                elif isinstance(cColor, list):
                                    cColor = QColor(*cColor)

                            classes.append(ClassInfo(label=int(item[0]), name=str(item[1]), color=cColor))
                        classes = sorted(classes, key=lambda c: c.label())
                        scheme = ClassificationScheme()
                        for classInfo in classes:
                            scheme.insertClass(classInfo)
                        classConfig = classSchemeToConfig(scheme)

                        self.setEditorWidgetSetup(fieldIndex,
                                                  QgsEditorWidgetSetup(ClassEditorKey, classConfig))

                        s = ""
                    if 'no data value' in fieldProperties.keys():
                        defaultValue = QgsDefaultValue('{}'.format(fieldProperties['no data value']))
                        field.setDefaultValueDefinition(defaultValue)
                        pass

                    if 'description' in fieldProperties.keys():
                        field.setComment(fieldProperties['description'])

            self.commitChanges()
        except Exception as ex:
            self.rollBack()
            print(ex, file=sys.stderr)

        if b:
            self.startEditing()

        return jsonData

    def copyEditorWidgetSetup(self, fields: typing.Union[QgsVectorLayer, typing.List[QgsField]]):
        """

        :param fields:
        :type fields:
        :return:
        :rtype:
        """
        """Copies the editor widget setup from another vector layer or list of QgsField"""
        if isinstance(fields, QgsVectorLayer):
            fields = fields.fields()

        for fSrc in fields:
            assert isinstance(fSrc, QgsField)
            idx = self.fields().indexOf(fSrc.name())

            if idx == -1:
                # field name does not exist
                continue
            fDst = self.fields().at(idx)
            assert isinstance(fDst, QgsField)

            setup = fSrc.editorWidgetSetup()
            if QgsGui.instance().editorWidgetRegistry().factory(setup.type()).supportsField(self, idx):
                self.setEditorWidgetSetup(idx, setup)

    def writeJSONProperties(self, pathSPECLIB: str):
        """
        Writes additional field properties into a JSON files
        :param pathSPECLIB:
        :return:
        """
        warnings.warn('will be removed in future', DeprecationWarning)
        assert isinstance(pathSPECLIB, str)
        if not pathSPECLIB.endswith('.json'):
            pathJSON = os.path.splitext(pathSPECLIB)[0] + '.json'
        else:
            pathJSON = pathSPECLIB
        jsonData = collections.OrderedDict()

        from ..classification.classificationscheme import EDITOR_WIDGET_REGISTRY_KEY, classSchemeFromConfig, ClassInfo

        rendererCategories = None

        # is this speclib rendered with a QgsCategorizedSymbolRenderer?
        if isinstance(self.renderer(), QgsCategorizedSymbolRenderer):
            rendererCategories = []
            for i, c in enumerate(self.renderer().categories()):
                symbol = c.symbol()
                assert isinstance(symbol, QgsSymbol)
                try:
                    label = int(c.value())
                except:
                    label = i
                category = [label, str(c.label()), symbol.color().name()]
                rendererCategories.append(category)
            jsonData[self.renderer().classAttribute()] = {'categories': rendererCategories}

        # is any field described as Raster Renderer or QgsCategorizedSymbolRenderer?
        for fieldIdx, field in enumerate(self.fields()):
            assert isinstance(field, QgsField)
            attributeEntry = dict()
            if len(field.comment()) > 0:
                attributeEntry['description'] = field.comment()

            defaultValue = field.defaultValueDefinition()
            assert isinstance(defaultValue, QgsDefaultValue)
            if len(defaultValue.expression()) > 0:
                attributeEntry['no data value'] = defaultValue.expression()

            setup = self.editorWidgetSetup(fieldIdx)
            assert isinstance(setup, QgsEditorWidgetSetup)
            if setup.type() == EDITOR_WIDGET_REGISTRY_KEY:
                conf = setup.config()
                classScheme = classSchemeFromConfig(conf)
                if len(classScheme) > 0:

                    categories = []
                    for classInfo in classScheme:
                        assert isinstance(classInfo, ClassInfo)
                        category = [classInfo.label(), classInfo.name(), classInfo.color().name()]
                        categories.append(category)
                    attributeEntry['categories'] = categories

            elif setup.type() == 'Classification' and isinstance(rendererCategories, list):
                attributeEntry['categories'] = rendererCategories

            if len(attributeEntry) > 0:
                jsonData[field.name()] = attributeEntry

        if len(jsonData) > 0:
            with open(pathJSON, 'w', encoding='utf-8') as f:
                json.dump(jsonData, f)

    @staticmethod
    def readFrom(uri, progressDialog: (QProgressDialog, ProgressHandler) = None):
        """
        Reads a Spectral Library from the source specified in "uri" (path, url, ...)
        :param uri: path or uri of the source from which to read SpectralProfiles and return them in a SpectralLibrary
        :return: SpectralLibrary
        """
        if isinstance(uri, QUrl):
            if uri.isLocalFile():
                uri = uri.toLocalFile()
            else:
                uri.toString()

        if isinstance(uri, str) and uri.endswith('.gpkg'):
            try:
                return SpectralLibrary(uri=uri)
            except Exception as ex:
                print(ex)
                return None

        readers = AbstractSpectralLibraryIO.subClasses()

        for cls in sorted(readers, key=lambda r: r.score(uri), reverse=True):
            try:
                if cls.canRead(uri):
                    sl = cls.readFrom(uri, progressDialog=progressDialog)
                    if isinstance(sl, SpectralLibrary):

                        if sl.name() in [DEFAULT_NAME, '']:
                            sl.setName(os.path.basename(uri))
                        return sl
            except Exception as ex:
                s = ""
        return None

    sigNameChanged = pyqtSignal(str)

    @classmethod
    def instances(cls) -> list:
        warnings.warn('SpectraLibrary.instances() Will be removed', DeprecationWarning)
        return []

    sigProgressInfo = pyqtSignal(int, int, str)
    sigProfileRendererChanged = pyqtSignal(SpectralProfileRenderer)

    def __init__(self,
                 name: str = DEFAULT_NAME,
                 uri: str = None):

        if isinstance(uri, pathlib.Path):
            uri = uri.as_posix()
        elif uri is None:
            # create a new, empty backend
            existing_vsi_files = vsiSpeclibs()
            assert isinstance(existing_vsi_files, list)
            i = 0
            uri = pathlib.PurePosixPath(VSI_DIR) / '{}.gpkg'.format(name)
            uri = uri.as_posix().replace('\\', '/')
            while uri in existing_vsi_files:
                i += 1
                uri = pathlib.PurePosixPath(VSI_DIR) / '{}{:03}.gpkg'.format(name, i)
                uri = uri.as_posix().replace('\\', '/')

            drv = ogr.GetDriverByName('GPKG')
            missingGPKGInfo = \
                "Your GDAL/OGR installation does not support the GeoPackage (GPKG) vector driver " + \
                "(https://gdal.org/drivers/vector/gpkg.html).\n" + \
                "Linux users might need to install libsqlite3."
            assert isinstance(drv, ogr.Driver), missingGPKGInfo

            co = ['VERSION=AUTO']
            dsSrc = drv.CreateDataSource(uri, options=co)
            assert isinstance(dsSrc, ogr.DataSource)
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(SPECLIB_EPSG_CODE)
            co = ['GEOMETRY_NAME=geom',
                  'GEOMETRY_NULLABLE=YES',
                  # 'FID=fid'
                  ]

            lyr = dsSrc.CreateLayer(name, srs=srs, geom_type=ogr.wkbPoint, options=co)

            assert isinstance(lyr, ogr.Layer)
            ldefn = lyr.GetLayerDefn()
            assert isinstance(ldefn, ogr.FeatureDefn)
            for f in ogrStandardFields():
                lyr.CreateField(f)

            try:
                dsSrc.FlushCache()
            except RuntimeError as rt:
                if 'failed: no such module: rtree' in str(rt):
                    pass
                else:
                    raise rt

        lyrOptions = QgsVectorLayer.LayerOptions(loadDefaultStyle=False, readExtentFromXml=False)
        super(SpectralLibrary, self).__init__(uri, name, 'ogr', lyrOptions)
        # consistency check
        fieldNames = self.fields().names()
        assert FIELD_NAME in fieldNames
        assert FIELD_VALUES in fieldNames
        f = self.fields().at(self.fields().lookupField(FIELD_NAME))
        assert f.type() == QVariant.String, 'Field {} not of type String / VARCHAR'
        f = self.fields().at(self.fields().lookupField(FIELD_VALUES))
        assert f.type() == QVariant.ByteArray, 'Field {} not of type ByteArray / BLOB'

        # self.beforeCommitChanges.connect(self.onBeforeCommitChanges)
        self.committedFeaturesAdded.connect(self.onCommittedFeaturesAdded)
        self.mProfileRenderer: SpectralProfileRenderer = SpectralProfileRenderer()
        self.mProfileRenderer.setInput(self)
        self.initTableConfig()
        self.initRenderer()

    def onCommittedFeaturesAdded(self, id, features):

        if id != self.id():
            return

        newFIDs = [f.id() for f in features]
        # see qgsvectorlayereditbuffer.cpp
        oldFIDs = list(reversed(list(self.editBuffer().addedFeatures().keys())))
        mFID2Style = self.profileRenderer().mFID2Style
        updates = dict()
        for fidOld, fidNew in zip(oldFIDs, newFIDs):
            if fidOld in mFID2Style.keys():
                updates[fidNew] = mFID2Style.pop(fidOld)
        mFID2Style.update(updates)

    def setProfileRenderer(self, profileRenderer: SpectralProfileRenderer):
        assert isinstance(profileRenderer, SpectralProfileRenderer)
        b = profileRenderer != self.mProfileRenderer
        self.mProfileRenderer = profileRenderer
        if b:
            self.sigProfileRendererChanged.emit(self.mProfileRenderer)

    def profileRenderer(self) -> SpectralProfileRenderer:
        return self.mProfileRenderer

    def initRenderer(self):
        """
        Initializes the default QgsFeatureRenderer
        """
        # color = speclibSettings().value('DEFAULT_PROFILE_COLOR', QColor('green'))
        # self.renderer().symbol().setColor(color)

        uri = self.source()
        uri = os.path.splitext(uri)[0] + '.qml'

        self.mProfileRenderer = SpectralProfileRenderer.default()
        self.mProfileRenderer.setInput(self)

        self.loadNamedStyle(uri)

    def initTableConfig(self):
        """
        Initializes the QgsAttributeTableConfig and further options
        """
        mgr = self.actions()
        assert isinstance(mgr, QgsActionManager)
        mgr.clearActions()

        # actionSetStyle = createSetPlotStyleAction(self.fields().at(self.fields().lookupField(FIELD_STYLE)))
        # assert isinstance(actionSetStyle, QgsAction)
        # mgr.addAction(actionSetStyle)

        actionRemoveSpectrum = createRemoveFeatureAction()
        assert isinstance(actionRemoveSpectrum, QgsAction)
        mgr.addAction(actionRemoveSpectrum)

        columns = self.attributeTableConfig().columns()
        visibleColumns = ['name']
        for column in columns:
            assert isinstance(column, QgsAttributeTableConfig.ColumnConfig)

            column.hidden = column.name not in visibleColumns and column.type != QgsAttributeTableConfig.Action

        # set column order
        c_action = [c for c in columns if c.type == QgsAttributeTableConfig.Action][0]
        c_name = [c for c in columns if c.name == FIELD_NAME][0]
        firstCols = [c_action, c_name]
        columns = [c_action, c_name] + [c for c in columns if c not in firstCols]

        conf = QgsAttributeTableConfig()
        conf.setColumns(columns)
        conf.setActionWidgetVisible(False)
        conf.setActionWidgetStyle(QgsAttributeTableConfig.ButtonList)

        self.setAttributeTableConfig(conf)

        # set special default editors
        # self.setEditorWidgetSetup(self.fields().lookupField(FIELD_STYLE), QgsEditorWidgetSetup(PlotSettingsEditorWidgetKey, {}))

        self.setEditorWidgetSetup(self.fields().lookupField(FIELD_VALUES),
                                  QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {}))

    def mimeData(self, formats: list = None) -> QMimeData:
        """
        Wraps this Speclib into a QMimeData object
        :return: QMimeData
        """
        if isinstance(formats, str):
            formats = [formats]
        elif formats is None:
            formats = [MIMEDATA_SPECLIB_LINK]

        mimeData = QMimeData()

        for format in formats:
            assert format in [MIMEDATA_SPECLIB_LINK, MIMEDATA_SPECLIB, MIMEDATA_TEXT, MIMEDATA_URL]
            if format == MIMEDATA_SPECLIB_LINK:
                global SPECLIB_CLIPBOARD
                thisID = id(self)
                SPECLIB_CLIPBOARD[thisID] = self

                mimeData.setData(MIMEDATA_SPECLIB_LINK, pickle.dumps(thisID))
            elif format == MIMEDATA_SPECLIB:
                mimeData.setData(MIMEDATA_SPECLIB, pickle.dumps(self))
            elif format == MIMEDATA_URL:
                mimeData.setUrls([QUrl(self.source())])
            elif format == MIMEDATA_TEXT:
                from .io.csvdata import CSVSpectralLibraryIO
                txt = CSVSpectralLibraryIO.asString(self)
                mimeData.setText(txt)

        return mimeData

    def optionalFields(self) -> list:
        """
        Returns the list of optional fields that are not part of the standard field set.
        :return: [list-of-QgsFields]
        """
        standardFields = createStandardFields()
        return [f for f in self.fields() if f not in standardFields]

    def optionalFieldNames(self) -> list:
        """
        Returns the names of additions fields / attributes
        :return: [list-of-str]
        """
        requiredFields = [f.name for f in ogrStandardFields()]
        return [n for n in self.fields().names() if n not in requiredFields]

    """
    def initConditionalStyles(self):
        styles = self.conditionalStyles()
        assert isinstance(styles, QgsConditionalLayerStyles)

        for fieldName in self.fieldNames():
            red = QgsConditionalStyle("@value is NULL")
            red.setTextColor(QColor('red'))
            styles.setFieldStyles(fieldName, [red])

        red = QgsConditionalStyle('﻿"__serialized__xvalues" is NULL OR "__serialized__yvalues is NULL" ')
        red.setBackgroundColor(QColor('red'))
        styles.setRowStyles([red])
    """

    def addMissingFields(self, fields: QgsFields, copyEditorWidgetSetup: bool = True):
        """
        :param fields: list of QgsFields
        :param copyEditorWidgetSetup: if True (default), the editor widget setup is copied for each field
        """
        missingFields = []
        for field in fields:
            assert isinstance(field, QgsField)
            i = self.fields().lookupField(field.name())
            if i == -1:
                missingFields.append(field)

        if len(missingFields) > 0:
            for fOld in missingFields:
                self.addAttribute(QgsField(fOld))

            if copyEditorWidgetSetup:
                self.copyEditorWidgetSetup(missingFields)

    def addSpeclib(self, speclib,
                   addMissingFields: bool = True,
                   copyEditorWidgetSetup: bool = True,
                   progressDialog: typing.Union[QProgressDialog, ProgressHandler] = None) -> typing.List[int]:
        """
        Adds profiles from another SpectraLibrary
        :param speclib: SpectralLibrary
        :param addMissingFields: if True (default), missing fields / attributes will be added automatically
        :param copyEditorWidgetSetup: if True (default), the editor widget setup will be copied for each added field
        :param progressDialog: QProgressDialog or qps.speclib.core.ProgressHandler

        :returns: set of added feature ids
        """
        assert isinstance(speclib, SpectralLibrary)

        fids_old = sorted(speclib.allFeatureIds(), key=lambda i: abs(i))
        fids_new = self.addProfiles(speclib,
                                    addMissingFields=addMissingFields,
                                    copyEditorWidgetSetup=copyEditorWidgetSetup,
                                    progressDialog=progressDialog)

        fid2Style = copy.deepcopy(speclib.profileRenderer().mFID2Style)

        for fid_old, fid_new in [(fo, fn) for fo, fn in zip(fids_old, fids_new) if fo in fid2Style.keys()]:
            self.profileRenderer().mFID2Style[fid_new] = fid2Style[fid_old]

        return fids_new

    def addProfiles(self, profiles: typing.Union[typing.List[SpectralProfile], QgsVectorLayer],
                    addMissingFields: bool = None, \
                    copyEditorWidgetSetup: bool = True, \
                    progressDialog: typing.Union[QProgressDialog, ProgressHandler] = None) -> typing.List[int]:

        if isinstance(profiles, SpectralProfile):
            profiles = [profiles]

        if addMissingFields is None:
            addMissingFields = isinstance(profiles, SpectralLibrary)

        if len(profiles) == 0:
            return

        assert self.isEditable(), 'SpectralLibrary "{}" is not editable. call startEditing() first'.format(self.name())

        keysBefore = set(self.editBuffer().addedFeatures().keys())

        lastTime = datetime.datetime.now()
        dt = datetime.timedelta(seconds=2)

        if isinstance(progressDialog, (QProgressDialog, ProgressHandler)):
            progressDialog.setLabelText('Add {} profiles'.format(len(profiles)))
            progressDialog.setValue(0)
            progressDialog.setRange(0, len(profiles))

        iSrcList = []
        iDstList = []

        bufferLength = 1000
        profileBuffer = []

        nAdded = 0

        def flushBuffer(triggerProgressBar: bool = False):
            nonlocal self, nAdded, profileBuffer, progressDialog, lastTime, dt
            if not self.addFeatures(profileBuffer):
                self.raiseError()
            nAdded += len(profileBuffer)
            profileBuffer.clear()

            if isinstance(progressDialog, (QProgressDialog, ProgressHandler)):
                # update progressbar in intervals of dt
                if triggerProgressBar or (lastTime + dt) < datetime.datetime.now():
                    progressDialog.setValue(nAdded)
                    lastTime = datetime.datetime.now()

        for i, pSrc in enumerate(profiles):
            if i == 0:
                if addMissingFields:
                    self.addMissingFields(pSrc.fields(), copyEditorWidgetSetup=copyEditorWidgetSetup)

                for iSrc, srcName in enumerate(pSrc.fields().names()):
                    if srcName == FIELD_FID:
                        continue
                    iDst = self.fields().lookupField(srcName)
                    if iDst >= 0:
                        iSrcList.append(iSrc)
                        iDstList.append(iDst)
                    elif addMissingFields:
                        raise Exception('Missing field: "{}"'.format(srcName))

            # create new feature + copy geometry
            pDst = QgsFeature(self.fields())
            pDst.setGeometry(pSrc.geometry())

            # copy attributes
            for iSrc, iDst in zip(iSrcList, iDstList):
                pDst.setAttribute(iDst, pSrc.attribute(iSrc))

            profileBuffer.append(pDst)

            if len(profileBuffer) >= bufferLength:
                flushBuffer()

        # final buffer call
        flushBuffer(triggerProgressBar=True)

        # return the edited features
        MAP = self.editBuffer().addedFeatures()
        fids_inserted = [MAP[k].id() for k in reversed(list(MAP.keys())) if k not in keysBefore]
        return fids_inserted

    def speclibFromFeatureIDs(self, fids):
        if isinstance(fids, int):
            fids = [fids]
        assert isinstance(fids, list)

        profiles = list(self.profiles(fids))

        speclib = SpectralLibrary()
        speclib.startEditing()
        speclib.addMissingFields(self.fields())
        speclib.addProfiles(profiles)
        speclib.commitChanges()
        return speclib

    def removeProfiles(self, profiles):
        """
        Removes profiles from this ProfileSet
        :param profiles: Profile or [list-of-profiles] to be removed
        :return: [list-of-remove profiles] (only profiles that existed in this set before)
        """
        if not isinstance(profiles, list):
            profiles = [profiles]

        for p in profiles:
            assert isinstance(p, SpectralProfile)

        fids = [p.id() for p in profiles]
        if len(fids) == 0:
            return

        assert self.isEditable()
        self.deleteFeatures(fids)

    def features(self, fids=None) -> QgsFeatureIterator:
        """
        Returns the QgsFeatures stored in this QgsVectorLayer
        :param fids: optional, [int-list-of-feature-ids] to return
        :return: QgsFeatureIterator
        """
        featureRequest = QgsFeatureRequest()
        if fids is not None:
            if isinstance(fids, int):
                fids = [fids]
            if not isinstance(fids, list):
                fids = list(fids)
            for fid in fids:
                assert isinstance(fid, int)
            featureRequest.setFilterFids(fids)
        # features = [f for f in self.features() if f.id() in fidsToRemove]
        return self.getFeatures(featureRequest)

    def profile(self, fid: int) -> SpectralProfile:
        return SpectralProfile.fromSpecLibFeature(self.getFeature(fid))

    def profiles(self, fids=None) -> typing.Generator[SpectralProfile, None, None]:
        """
        Like features(fidsToRemove=None), but converts each returned QgsFeature into a SpectralProfile
        :param fids: optional, [int-list-of-feature-ids] to return
        :return: generator of [List-of-SpectralProfiles]
        """
        for f in self.features(fids=fids):
            yield SpectralProfile.fromSpecLibFeature(f)

    def groupBySpectralProperties(self, excludeEmptyProfiles=True):
        """
        Returns SpectralProfiles grouped by key = (xValues, xUnit and yUnit):

            xValues: None | [list-of-xvalues with n>0 elements]
            xUnit: None | str with len(str) > 0, e.g. a wavelength like 'nm'
            yUnit: None | str with len(str) > 0, e.g. 'reflectance' or '-'

        :return: {(xValues, xUnit, yUnit):[list-of-profiles]}
        """

        results = dict()
        for p in self.profiles():
            assert isinstance(p, SpectralProfile)

            d = p.values()

            if excludeEmptyProfiles:
                if not isinstance(d['y'], list):
                    continue
                if not len(d['y']) > 0:
                    continue

            x = tuple(p.xValues())
            if len(x) == 0:
                x = None
            # y = None if d['y'] in [None, []] else tuple(d['y'])

            xUnit = None if d['xUnit'] in [None, ''] else d['xUnit']
            yUnit = None if d['yUnit'] in [None, ''] else d['yUnit']

            key = (x, xUnit, yUnit)

            if key not in results.keys():
                results[key] = []
            results[key].append(p)
        return results

    def exportNamedStyle(self,
                         doc: QDomDocument,
                         context: QgsReadWriteContext,
                         categories: QgsMapLayer.StyleCategories
                         ) -> str:

        msg = super(SpectralLibrary, self).exportNamedStyle(doc, context=context, categories=categories)
        if msg == '':
            qgsNode = doc.documentElement().toElement()
            speclibNode = doc.createElement(XMLNODE_PROFILE_RENDERER)
            self.mProfileRenderer.writeXml(speclibNode, doc)
            qgsNode.appendChild(speclibNode)

        return msg

    def importNamedStyle(self, doc: QDomDocument,
                         categories: QgsMapLayer.StyleCategories = QgsMapLayer.AllStyleCategories):

        success, errorMsg = super(SpectralLibrary, self).importNamedStyle(doc, categories)
        if success:
            elem = doc.documentElement().firstChildElement(XMLNODE_PROFILE_RENDERER)
            if not elem.isNull():
                from .gui import SpectralProfileRenderer
                scheme = SpectralProfileRenderer.readXml(elem)
                if isinstance(scheme, SpectralProfileRenderer):
                    self.mProfileRenderer = scheme
                    self.mProfileRenderer.setInput(self)
        return success, errorMsg

    def exportProfiles(self, *args, **kwds) -> list:
        warnings.warn('Use SpectralLibrary.write() instead', DeprecationWarning)
        return self.write(*args, **kwds)

    def write(self, path: str, **kwds) -> typing.List[str]:
        """
        Exports profiles to a file.
        This wrapper tries to identify a fitting AbstractSpectralLibraryIO from the
        file extension in `path`.
        To ensure the way how the SpectralLibrary is written into file data, use
        a AbstractSpectralLibraryIO implementation of choice.
        :param path: str, filepath
        :param kwds: keywords to be used in specific `AbstractSpectralLibraryIO.write(...)` methods.
        :return: list of written files
        """

        if path is None:
            path, filter = QFileDialog.getSaveFileName(parent=kwds.get('parent'),
                                                       caption='Save Spectral Library',
                                                       directory='speclib',
                                                       filter=FILTERS)

        if isinstance(path, pathlib.Path):
            path = path.as_posix()

        if len(path) > 0:
            ext = os.path.splitext(path)[-1].lower()
            from .io.csvdata import CSVSpectralLibraryIO
            from .io.vectorsources import VectorSourceSpectralLibraryIO
            from .io.envi import EnviSpectralLibraryIO

            # todo: implement filter strings in AbstractSpectralLibraryIOs to auto-match file extensions
            if ext in ['.sli', '.esl']:
                return EnviSpectralLibraryIO.write(self, path, **kwds)

            elif ext in ['.json', '.geojson', '.geojsonl', '.csv', '.gpkg']:
                return VectorSourceSpectralLibraryIO.write(self, path, **kwds)

        return []

    def yRange(self):
        profiles = self.profiles()
        minY = min([min(p.yValues()) for p in profiles])
        maxY = max([max(p.yValues()) for p in profiles])
        return minY, maxY

    def __repr__(self):
        return str(self.__class__) + '"{}" {} feature(s)'.format(self.name(), self.dataProvider().featureCount())

    def plot(self):
        """Create a plot widget and shows all SpectralProfile in this SpectralLibrary."""
        from ..externals import pyqtgraph as pg
        pg.mkQApp()

        win = pg.GraphicsWindow(title="Spectral Library")
        win.resize(1000, 600)

        # Enable antialiasing for prettier plots
        pg.setConfigOptions(antialias=True)

        # Create a plot with some random data
        p1 = win.addPlot(title="Spectral Library {}".format(self.name()), pen=0.5)
        yMin, yMax = self.yRange()
        p1.setYRange(yMin, yMax)

        # Add three infinite lines with labels
        for p in self:
            pi = pg.PlotDataItem(p.xValues(), p.yValues())
            p1.addItem(pi)

        pg.QAPP.exec_()

    def fieldNames(self) -> list:
        """
        Retunrs the field names. Shortcut from self.fields().names()
        :return: [list-of-str]
        """
        return self.fields().names()

    def __reduce_ex__(self, protocol):
        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        """
        Pickles a SpectralLibrary
        :return: pickle dump
        """

        fields = qgsFields2str(self.fields())
        data = []
        for feature in self.features():
            data.append((feature.geometry().asWkt(),
                         qgsFieldAttributes2List(feature.attributes())
                         ))

        dump = pickle.dumps((self.name(), fields, data))
        return dump
        # return self.__dict__.copy()

    def __setstate__(self, state):
        """
        Restores a pickled SpectralLibrary
        :param state:
        :return:
        """
        name, fields, data = pickle.loads(state)
        self.setName(name)
        fieldNames = self.fieldNames()
        dataFields = str2QgsFields(fields)
        fieldsToAdd = [f for f in dataFields if f.name() not in fieldNames]
        self.startEditing()
        if len(fieldsToAdd) > 0:

            for field in fieldsToAdd:
                assert isinstance(field, QgsField)
                self.fields().append(field)
            self.commitChanges()
            self.startEditing()

        fieldNames = self.fieldNames()
        order = [fieldNames.index(f.name()) for f in dataFields]
        reoder = list(range(len(dataFields))) != order

        features = []
        nextFID = self.allFeatureIds()
        nextFID = max(nextFID) if len(nextFID) else 0

        for i, datum in enumerate(data):
            nextFID += 1
            wkt, attributes = datum
            feature = QgsFeature(self.fields(), nextFID)
            if reoder:
                attributes = [attributes[i] for i in order]
            feature.setAttributes(attributes)
            feature.setAttribute(FIELD_FID, nextFID)
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
            features.append(feature)
        self.addFeatures(features)
        self.commitChanges()

    def __len__(self) -> int:
        cnt = self.featureCount()
        # can be -1 if the number of features is unknown
        return max(cnt, 0)

    def __iter__(self):
        r = QgsFeatureRequest()
        for f in self.getFeatures(r):
            yield SpectralProfile.fromSpecLibFeature(f)

    def __getitem__(self, slice) -> typing.Union[SpectralProfile, typing.List[SpectralProfile]]:
        fids = sorted(self.allFeatureIds())[slice]

        if isinstance(fids, list):
            return sorted(self.profiles(fids=fids), key=lambda p: p.id())
        else:
            return SpectralProfile.fromSpecLibFeature(self.getFeature(fids))

    def __delitem__(self, slice):
        profiles = self[slice]
        self.removeProfiles(profiles)

    def __eq__(self, other):
        if not isinstance(other, SpectralLibrary):
            return False

        if len(self) != len(other):
            return False

        for p1, p2 in zip(self.__iter__(), other.__iter__()):
            if not p1 == p2:
                return False
        return True

    def __hash__(self):
        # return super(SpectralLibrary, self).__hash__()
        return hash(self.id())


class AbstractSpectralLibraryIO(object):
    """
    Abstract class interface to define I/O operations for spectral libraries
    """
    _SUB_CLASSES = []

    @staticmethod
    def subClasses():

        from .io.vectorsources import VectorSourceSpectralLibraryIO
        from .io.artmo import ARTMOSpectralLibraryIO
        from .io.asd import ASDSpectralLibraryIO
        from .io.clipboard import ClipboardIO
        from .io.csvdata import CSVSpectralLibraryIO
        from .io.ecosis import EcoSISSpectralLibraryIO
        from .io.envi import EnviSpectralLibraryIO
        from .io.specchio import SPECCHIOSpectralLibraryIO

        subClasses = [
            VectorSourceSpectralLibraryIO,  # this is the prefered way to save/load speclibs
            EnviSpectralLibraryIO,
            ASDSpectralLibraryIO,
            CSVSpectralLibraryIO,
            ARTMOSpectralLibraryIO,
            EcoSISSpectralLibraryIO,
            SPECCHIOSpectralLibraryIO,
            ClipboardIO,
        ]

        # other sub-classes
        for c in AbstractSpectralLibraryIO.__subclasses__():
            if c not in subClasses:
                subClasses.append(c)

        return subClasses

    @classmethod
    def canRead(cls, path: str) -> bool:
        """
        Returns true if it can read the source defined by path.
        Well behaving implementations use a try-catch block and return False in case of errors.
        :param path: source uri
        :return: True, if source is readable.
        """
        return False

    @classmethod
    def readFrom(cls, path: str,
                 progressDialog: typing.Union[QProgressDialog, ProgressHandler] = None) -> SpectralLibrary:
        """
        Returns the SpectralLibrary read from "path"
        :param path: source of Spectral Library
        :param progressDialog: QProgressDialog, which well-behave implementations can use to show the import progress.
        :return: SpectralLibrary
        """
        return None

    @classmethod
    def write(cls,
              speclib: SpectralLibrary,
              path: str,
              progressDialog: typing.Union[QProgressDialog, ProgressHandler] = None) -> \
            typing.List[str]:
        """
        Writes the SpectralLibrary.
        :param speclib: SpectralLibrary to write
        :param path: file path to write the SpectralLibrary to
        :param progressDialog:  QProgressDialog, which well-behave implementations can use to show the writing progress.
        :return: a list of paths that can be used to re-open all written profiles
        """
        assert isinstance(speclib, SpectralLibrary)
        return []

    @classmethod
    def supportedFileExtensions(cls) -> typing.Dict[str, str]:
        """
        Returns a dictionary of file extensions (key) and descriptions (values)
        that can be read/written by the AbstractSpectralLibraryIO implementation.
        :return: dict[str,str]
        """
        return dict()

    @classmethod
    def filterString(cls) -> str:
        """
        Returns a filter string to be used in QFileDialogs
        :return: str
        """
        return ';;'.join([f'{descr} (*{ext})' for ext, descr
                          in cls.supportedFileExtensions().items()])

    @classmethod
    def score(cls, uri: str) -> int:
        uri = str(uri)
        """
        Returns a score value for the give uri. E.g. 0 for unlikely/unknown, 20 for yes, probably thats the file format the reader can read.

        :param uri: str
        :return: int
        """
        for ext in cls.supportedFileExtensions().keys():
            if uri.endswith(ext):
                return 20
        return 0

    @classmethod
    def addImportActions(cls, spectralLibrary: SpectralLibrary, menu: QMenu):
        """
        Returns a list of QActions or QMenus that can be called to read/import SpectralProfiles from a certain file format into a SpectralLibrary
        :param spectralLibrary: SpectralLibrary to import SpectralProfiles to
        :return: [list-of-QAction-or-QMenus]
        """
        return []

    @classmethod
    def addExportActions(cls, spectralLibrary: SpectralLibrary, menu: QMenu):
        """
        Returns a list of QActions or QMenus that can be called to write/export SpectralProfiles into certain file format
        :param spectralLibrary: SpectralLibrary to export SpectralProfiles from
        :return: [list-of-QAction-or-QMenus]
        """
        return []


def deleteSelected(layer):
    assert isinstance(layer, QgsVectorLayer)
    b = layer.isEditable()

    layer.startEditing()
    layer.beginEditCommand('Delete selected features')
    layer.deleteSelectedFeatures()
    layer.endEditCommand()

    if not b:
        layer.commitChanges()

    # saveEdits(layer, leaveEditable=b)