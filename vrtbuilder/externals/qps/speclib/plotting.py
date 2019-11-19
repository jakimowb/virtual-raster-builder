# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    plotting.py
    Functionality to plot SpectralLibraries
    ---------------------
    Date                 : Okt 2018
    Copyright            : (C) 2018 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This file is part of the EnMAP-Box.                                   *
*                                                                         *
*   The EnMAP-Box is free software; you can redistribute it and/or modify *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 3 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
*   The EnMAP-Box is distributed in the hope that it will be useful,      *
*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the          *
*   GNU General Public License for more details.                          *
*                                                                         *
*   You should have received a copy of the GNU General Public License     *
*   along with the EnMAP-Box. If not, see <http://www.gnu.org/licenses/>. *
*                                                                         *
***************************************************************************
"""
import sys, re, os, collections
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.gui import *
from qgis.core import *
from ..externals.pyqtgraph.functions import mkPen
from ..externals import pyqtgraph as pg
from ..externals.pyqtgraph.graphicsItems.PlotDataItem import PlotDataItem
from ..utils import METRIC_EXPONENTS, convertMetricUnit
from .spectrallibraries import SpectralProfile, SpectralLibrary, MIMEDATA_SPECLIB_LINK, FIELD_VALUES

BAND_INDEX = 'Band Index'


class SpectralXAxis(pg.AxisItem):

    def __init__(self, *args, **kwds):
        super(SpectralXAxis, self).__init__(*args, **kwds)
        self.setRange(1, 3000)
        self.enableAutoSIPrefix(True)
        self.labelAngle = 0


class SpectralLibraryPlotItem(pg.PlotItem):

    def __init__(self, *args, **kwds):
        super(SpectralLibraryPlotItem, self).__init__(*args, **kwds)

    def addItems(self, items: list, *args, **kargs):
        """
        Add a graphics item to the view box.
        If the item has plot data (PlotDataItem, PlotCurveItem, ScatterPlotItem), it may
        be included in analysis performed by the PlotItem.
        """
        if len(items) == 0:
            return

        self.items.extend(items)
        vbargs = {}
        if 'ignoreBounds' in kargs:
            vbargs['ignoreBounds'] = kargs['ignoreBounds']
        self.vb.addItems(items, *args, **vbargs)
        # name = None
        refItem = items[0]
        if hasattr(refItem, 'implements') and refItem.implements('plotData'):
            # name = item.name()
            self.dataItems.extend(items)
            # self.plotChanged()

            for item in items:
                self.itemMeta[item] = kargs.get('params', {})
            # item.setMeta(params)
            self.curves.extend(items)
            # self.addItem(c)

        # if hasattr(item, 'setLogMode'):
        #    item.setLogMode(self.ctrl.logXCheck.isChecked(), self.ctrl.logYCheck.isChecked())

        if isinstance(refItem, PlotDataItem):
            ## configure curve for this plot
            (alpha, auto) = self.alphaState()

            for item in items:
                item.setAlpha(alpha, auto)
                item.setFftMode(self.ctrl.fftCheck.isChecked())
                item.setDownsampling(*self.downsampleMode())
                item.setClipToView(self.clipToViewMode())
                item.setPointMode(self.pointMode())

            ## Hide older plots if needed
            self.updateDecimation()

            ## Add to average if needed
            self.updateParamList()
            if self.ctrl.averageGroup.isChecked() and 'skipAverage' not in kargs:
                self.addAvgCurve(item)

            # c.connect(c, QtCore.SIGNAL('plotChanged'), self.plotChanged)
            # item.sigPlotChanged.connect(self.plotChanged)
            # self.plotChanged()
        # name = kargs.get('name', getattr(item, 'opts', {}).get('name', None))
        # if name is not None and hasattr(self, 'legend') and self.legend is not None:
        #    self.legend.addItem(item, name=name)


class SpectralProfilePlotDataItem(PlotDataItem):
    """
    A pyqtgraph.PlotDataItem to plot SpectralProfiles
    """

    def __init__(self, spectralProfile: SpectralProfile):
        assert isinstance(spectralProfile, SpectralProfile)
        super(SpectralProfilePlotDataItem, self).__init__()

        self.mXValueConversionFunction = lambda v, *args: v
        self.mYValueConversionFunction = lambda v, *args: v

        self.mDefaultLineWidth = self.pen().width()
        self.mDefaultLineColor = None

        self.mProfile = None
        self.mInitialDataX = None
        self.mInitialDataY = None
        self.mInitialUnitX = None
        self.mInitialUnitY = None

        self.initProfile(spectralProfile)
        self.applyMapFunctions()

    def initProfile(self, spectralProfile: SpectralProfile):
        """
        Initializes internal spectral profile settings
        :param spectralProfile: SpectralProfile
        """
        assert isinstance(spectralProfile, SpectralProfile)
        self.mProfile = spectralProfile
        self.mInitialDataX = spectralProfile.xValues()
        self.mInitialDataY = spectralProfile.yValues()
        self.mInitialUnitX = spectralProfile.xUnit()
        self.mInitialUnitY = spectralProfile.yUnit()
        for v in [self.mInitialDataX, self.mInitialDataY]:
            assert isinstance(v, list)

    def resetSpectralProfile(self, spectralProfile: SpectralProfile = None):
        """
        Resets internal settings to either the original SpectraProfile or a new one
        :param spectralProfile: a new SpectralProfile
        """
        """

        Use this to account for changes profile values.
        """
        sp = spectralProfile if isinstance(spectralProfile, SpectralProfile) else self.spectralProfile()
        self.initProfile(sp)
        self.applyMapFunctions()

    def spectralProfile(self) -> SpectralProfile:
        """
        Returns the SpectralProfile
        :return: SpectralPrrofile
        """
        return self.mProfile

    def setMapFunctionX(self, func):
        """
        Sets the function `func` to get the values to be plotted on x-axis.
        The function must have the pattern mappedXValues = func(originalXValues, SpectralProfilePlotDataItem),
        The default function `func = lambda v, *args : v` returns the unchanged x-values in `v`
        :param func: callable, mapping function
        """
        assert callable(func)
        self.mXValueConversionFunction = func

    def setMapFunctionY(self, func):
        """
        Sets the function `func` to get the values to be plotted on y-axis.
        The function must follow the pattern mappedYValues = func(originalYValues, plotDataItem),
        The default function `func = lambda v, *args : v` returns the unchanged y-values in `v`
        The second argument `plotDataItem` provides a handle to SpectralProfilePlotDataItem instance which uses this
        function when running its `.applyMapFunctions()`.
        :param func: callable, mapping function
        """
        assert callable(func)
        self.mYValueConversionFunction = func

    def applyMapFunctions(self) -> bool:
        """
        Applies the two functions defined with `.setMapFunctionX` and `.setMapFunctionY`.
        :return: bool, True in case of success
        """
        success = False
        if len(self.mInitialDataX) > 0 and len(self.mInitialDataY) > 0:
            x = None
            y = None

            try:
                x = self.mXValueConversionFunction(self.mInitialDataX, self)
                y = self.mYValueConversionFunction(self.mInitialDataY, self)
                if isinstance(x, list) and isinstance(y, list) and len(x) > 0 and len(y) > 0:
                    success = True
            except Exception as ex:
                print(ex)
                pass

        if success:
            self.setData(x=x, y=y)
            self.setVisible(True)
        else:
            # self.setData(x=[], y=[])
            self.setVisible(False)

        return success

    def id(self) -> int:
        """
        Returns the profile id
        :return: int
        """
        return self.mProfile.id()

    def setClickable(self, b: bool, width=None):
        """

        :param b:
        :param width:
        :return:
        """
        assert isinstance(b, bool)
        self.curve.setClickable(b, width=width)

    def setSelected(self, b: bool):
        """
        Sets if this profile should appear as "selected"
        :param b: bool
        """

        if b:
            self.setLineWidth(self.mDefaultLineWidth + 3)
            # self.setColor(Qgis.DEFAULT_HIGHLIGHT_COLOR)
        else:
            self.setLineWidth(self.mDefaultLineWidth)
            # self.setColor(self.mDefaultLineColor)

    def setColor(self, color: QColor):
        """
        Sets the profile color
        :param color: QColor
        """
        if not isinstance(color, QColor):
            color = QColor(color)

        self.setPen(color)

        if not isinstance(self.mDefaultLineColor, QColor):
            self.mDefaultLineColor = color

    def pen(self):
        """
        Returns the QPen of the profile
        :return: QPen
        """
        return mkPen(self.opts['pen'])

    def color(self):
        """
        Returns the profile color
        :return: QColor
        """
        return self.pen().color()

    def setLineWidth(self, width):
        """
        Set the profile width in px
        :param width: int
        """
        pen = mkPen(self.opts['pen'])
        assert isinstance(pen, QPen)
        pen.setWidth(width)
        self.setPen(pen)

    def mouseClickEvent(self, ev):
        if ev.button() == Qt.RightButton:
            if self.raiseContextMenu(ev):
                ev.accept()

    def raiseContextMenu(self, ev):
        menu = self.contextMenu()

        # Let the scene add on to the end of our context menu
        # (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, ev)

        pos = ev.screenPos()
        menu.popup(QPoint(pos.x(), pos.y()))
        return True

    # This method will be called when this item's _children_ want to raise
    # a context menu that includes their parents' menus.
    def contextMenu(self, event=None):

        self.menu = QMenu()
        self.menu.setTitle(self.name + " options..")

        green = QAction("Turn green", self.menu)
        green.triggered.connect(self.setGreen)
        self.menu.addAction(green)
        self.menu.green = green

        blue = QAction("Turn blue", self.menu)
        blue.triggered.connect(self.setBlue)
        self.menu.addAction(blue)
        self.menu.green = blue

        alpha = QWidgetAction(self.menu)
        alphaSlider = QSlider()
        alphaSlider.setOrientation(Qt.Horizontal)
        alphaSlider.setMaximum(255)
        alphaSlider.setValue(255)
        alphaSlider.valueChanged.connect(self.setAlpha)
        alpha.setDefaultWidget(alphaSlider)
        self.menu.addAction(alpha)
        self.menu.alpha = alpha
        self.menu.alphaSlider = alphaSlider
        return self.menu


class SpectralLibraryPlotWidget(pg.PlotWidget):
    """
    A widget to PlotWidget SpectralProfiles
    """

    def __init__(self, parent=None):
        super(SpectralLibraryPlotWidget, self).__init__(parent)

        self.mViewBox = SpectralViewBox()
        plotItem = SpectralLibraryPlotItem(
            axisItems={'bottom': SpectralXAxis(orientation='bottom')}
            , viewBox=self.mViewBox
        )
        self.centralWidget.setParent(None)
        self.centralWidget = None
        self.setCentralWidget(plotItem)
        self.plotItem = plotItem
        for m in ['addItem', 'removeItem', 'autoRange', 'clear', 'setXRange',
                  'setYRange', 'setRange', 'setAspectLocked', 'setMouseEnabled',
                  'setXLink', 'setYLink', 'enableAutoRange', 'disableAutoRange',
                  'setLimits', 'register', 'unregister', 'viewRect']:
            setattr(self, m, getattr(self.plotItem, m))
        # QtCore.QObject.connect(self.plotItem, QtCore.SIGNAL('viewChanged'), self.viewChanged)
        self.plotItem.sigRangeChanged.connect(self.viewRangeChanged)

        pi = self.getPlotItem()
        assert isinstance(pi, pg.PlotItem) and pi == plotItem and pi == self.plotItem
        #pi.disableAutoRange()


        self.mSpeclib = None
        self.mSpeclibSignalConnections = []

        self.mUpdatesBlocked = False

        self.mXUnitInitialized = False
        self.mXUnit = BAND_INDEX
        self.mYUnit = None

        # describe function to convert length units from unit a to unit b
        self.mLUT_UnitConversions = dict()
        returnNone = lambda v, *args: None
        returnSame = lambda v, *args: v
        self.mLUT_UnitConversions[(None, None)] = returnSame
        keys = list(METRIC_EXPONENTS.keys())
        exponents = list(METRIC_EXPONENTS.values())

        for key in keys:
            self.mLUT_UnitConversions[(None, key)] = returnNone
            self.mLUT_UnitConversions[(key, None)] = returnNone
            self.mLUT_UnitConversions[(key, key)] = returnSame

        for i, key1 in enumerate(keys[0:]):
            e1 = exponents[i]
            for key2 in keys[i + 1:]:
                e2 = exponents[keys.index(key2)]
                if e1 == e2:
                    self.mLUT_UnitConversions[(key1, key2)] = returnSame

        self.mViewBox.sigXUnitChanged.connect(self.setXUnit)

        self.mPlotDataItems = dict()
        self.setAntialiasing(True)
        self.setAcceptDrops(True)
        self.mMaxProfiles = 256
        self.mPlotOverlayItems = []

        self.mAddedFeatureList = []

        self.mUpdateTimer = QTimer()
        #self.mUpdateTimer.timeout.connect(self._addedFeatureCheck)
        self.mUpdateTimer.setInterval(2000)
        self.mUpdateTimer.start(2000)

        self.mCrosshairLineV = pg.InfiniteLine(angle=90, movable=False)
        self.mCrosshairLineH = pg.InfiniteLine(angle=0, movable=False)

        self.mInfoLabelCursor = pg.TextItem(text='<cursor position>', anchor=(1.0, 0.0))
        self.mCrosshairLineH.pen.setWidth(2)
        self.mCrosshairLineV.pen.setWidth(2)
        self.mCrosshairLineH.setZValue(9999999)
        self.mCrosshairLineV.setZValue(9999999)
        self.mInfoLabelCursor.setZValue(9999999)

        self.scene().addItem(self.mInfoLabelCursor)
        self.mInfoLabelCursor.setParentItem(self.getPlotItem())

        pi.addItem(self.mCrosshairLineV, ignoreBounds=True)
        pi.addItem(self.mCrosshairLineH, ignoreBounds=True)

        self.setBackground(QColor('black'))
        self.mInfoColor = None
        self.setInfoColor(QColor('yellow'))

        self.proxy2D = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=100, slot=self.onMouseMoved2D)


        # set default axis unit
        self.setXLabel(self.mViewBox.xAxisUnit())
        self.setYLabel('Y (Spectral Value)')

        self.mViewBox.sigXUnitChanged.connect(self.updateXUnit)

    def setInfoColor(self, color: QColor):
        if isinstance(color, QColor):
            self.mInfoColor = color
            self.mInfoLabelCursor.setColor(self.mInfoColor)
            self.mCrosshairLineH.pen.setColor(self.mInfoColor)
            self.mCrosshairLineV.pen.setColor(self.mInfoColor)

    def infoColor(self) -> QColor:
        """
        Returns the color of overlotted information
        :return: QColor
        """
        return QColor(self.mInfoColor)

    def foregroundInfoColor(self) -> QColor:
        return self.plotItem.axes['bottom']['item'].pen().color()

    def setForegroundInfoColor(self, color: QColor):
        if isinstance(color, QColor):
            for axis in self.plotItem.axes.values():

                ai = axis['item']
                if isinstance(ai, pg.AxisItem):
                    ai.setPen(QColor(color))

    def updatesBlocked(self) -> bool:
        """
        Returns whether speclib updates are shown in the plot widget or not
        :return: bool
        """
        return self.mUpdatesBlocked

    def blockUpdates(self, b: bool) -> bool:
        """
        Disconnect the plot widget from spectral library signales.
        :param b:
        :return:
        """
        b0 = self.updatesBlocked()
        self.mUpdatesBlocked = b

        if b == True:
            self.disconnectSpeclibSignals()
            self.blockSignals(True)
            #self.updatePlot()
            self.setViewportUpdateMode(QGraphicsView.NoViewportUpdate)
        else:
            self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
            self.blockSignals(False)
            self.connectSpeclibSignals()

        return b0

    def onMouseMoved2D(self, evt):
        pos = evt[0]  ## using signal proxy turns original arguments into a tuple

        plotItem = self.getPlotItem()
        if plotItem.sceneBoundingRect().contains(pos):
            vb = plotItem.vb
            assert isinstance(vb, SpectralViewBox)
            mousePoint = vb.mapSceneToView(pos)
            x = mousePoint.x()
            if x >= 0:

                # todo: add infos about plot data below mouse, e.g. profile band number
                rect = QRectF(pos.x() - 2, pos.y() - 2, 5, 5)
                itemsBelow = plotItem.scene().items(rect)
                if SpectralProfilePlotDataItem in itemsBelow:
                    s = ""

                y = mousePoint.y()
                vb.updateCurrentPosition(x, y)
                self.mInfoLabelCursor.setText('x:{:0.5f}\ny:{:0.5f}'.format(x, y))

                s = self.size()
                pos = QPointF(s.width(), 0)
                self.mInfoLabelCursor.setVisible(vb.mActionShowCursorValues.isChecked())
                self.mInfoLabelCursor.setPos(pos)

                b = vb.mActionShowCrosshair.isChecked()
                self.mCrosshairLineH.setVisible(b)
                self.mCrosshairLineV.setVisible(b)
                self.mCrosshairLineV.setPos(mousePoint.x())
                self.mCrosshairLineH.setPos(mousePoint.y())

    def setPlotOverlayItems(self, items):
        """
        Adds a list of PlotItems to be overlayed
        :param items:
        :return:
        """
        if not isinstance(items, list):
            items = [items]
        assert isinstance(items, list)

        for item in items:
            assert isinstance(item, PlotDataItem)

        toRemove = self.mPlotOverlayItems[:]
        for item in toRemove:
            if item in self.plotItem.items:
                item
                self.plotItem.removeItem(item)

        self.mPlotOverlayItems.clear()
        self.mPlotOverlayItems.extend(items)
        for item in items:
            self.plotItem.addItem(item)

        if not self.mXUnitInitialized:

            xUnit = None
            for item in self.mPlotOverlayItems:
                if isinstance(item, SpectralProfilePlotDataItem):
                    if item.mInitialUnitX != self.mXUnit:
                        xUnit = item.mInitialUnitX

            if xUnit is not None:
                self.setXUnit(xUnit)
                self.mXUnitInitialized = True

    def _spectralProfilePDIs(self) -> list:
        return [i for i in self.getPlotItem().items if isinstance(i, SpectralProfilePlotDataItem)]

    def _removeSpectralProfilePDIs(self, pdis: list):

        pi = self.getPlotItem()
        assert isinstance(pi, pg.PlotItem)

        for pdi in pdis:
            assert isinstance(pdi, SpectralProfilePlotDataItem)
            pi.removeItem(pdi)
            assert pdi not in pi.dataItems
            if pdi.id() in self.mPlotDataItems.keys():
                self.mPlotDataItems.pop(pdi.id())

    def setSpeclib(self, speclib: SpectralLibrary):
        """
        Sets the SpectralLibrary to be visualized
        :param speclib: SpectralLibrary
        """
        assert isinstance(speclib, SpectralLibrary)

        self._removeSpectralProfilePDIs(self._spectralProfilePDIs())
        self.mSpeclib = speclib
        self.connectSpeclibSignals()
        self.onProfilesAdded(self.speclib().allFeatureIds())

        self.updatePlot()

    def connectSpeclibSignals(self):
        if isinstance(self.mSpeclib, SpectralLibrary):

            self.mSpeclib.featureAdded.connect(self.onProfilesAdded)
            self.mSpeclib.featuresDeleted.connect(self.onProfilesRemoved)
            self.mSpeclib.selectionChanged.connect(self.onSelectionChanged)
            self.mSpeclib.committedAttributeValuesChanges.connect(self.onCommittedAttributeValuesChanges)
            self.mSpeclib.rendererChanged.connect(self.onRendererChanged)


    def disconnectSpeclibSignals(self):

        if isinstance(self.mSpeclib, SpectralLibrary):
            def disconnect(sig, slot):
                while True:
                    try:
                        r = sig.disconnect(slot)
                        s = ""
                    except:
                        break
            disconnect(self.mSpeclib.featureAdded, self.onProfilesAdded)
            disconnect(self.mSpeclib.featuresDeleted, self.onProfilesRemoved)
            disconnect(self.mSpeclib.selectionChanged, self.onSelectionChanged)
            disconnect(self.mSpeclib.committedAttributeValuesChanges, self.onCommittedAttributeValuesChanges)
            disconnect(self.mSpeclib.rendererChanged, self.onRendererChanged)


    def _addedFeatureCheck(self):
        if len(self.mAddedFeatureList) > 0 and not self.mUpdatesBlocked:
            fids = self.mAddedFeatureList[:]
            self.mAddedFeatureList.clear()
            self.onProfilesAdded(fids)

    def _addAddedFeatureList(self, fid):
        self.mAddedFeatureList.append(fid)

    def speclib(self) -> SpectralLibrary:
        """
        Returns the SpectralLibrary this widget is linked to.
        :return: SpectralLibrary
        """

    def onCommittedAttributeValuesChanges(self, layerID, featureMap):
        """
        Reacts on changes in spectral values
        """
        s = ""

        if layerID != self.speclib().id():
            return

        idxF = self.speclib().fields().indexOf(FIELD_VALUES)
        fids = []

        for fid, fieldMap in featureMap.items():
            if idxF in fieldMap.keys():
                fids.append(fid)

        if len(fids) == 0:
            return
        for p in self.speclib().profiles(fids):
            assert isinstance(p, SpectralProfile)
            pdi = self.spectralProfilePlotDataItem(p.id())
            if isinstance(pdi, SpectralProfilePlotDataItem):
                pdi.resetSpectralProfile(p)

    @pyqtSlot()
    def onRendererChanged(self):

        profiles = self.mSpeclib.profiles(fids=self.mPlotDataItems.keys())
        self.updateProfileStyles(list(profiles))


    def onSelectionChanged(self, selected, deselected):

        for pdi in self.plotItem.items:
            if isinstance(pdi, SpectralProfilePlotDataItem):
                w = pdi.pen().width()
                if pdi.id() in selected:
                    pdi.setSelected(True)
                elif pdi.id() in deselected:
                    pdi.setSelected(False)
        s = ""

    def syncLibrary(self):
        s = ""
        # see https://groups.google.com/forum/#!topic/pyqtgraph/kz4U6dswEKg
        # speed problems in case of too many line items
        profiles = list(self.speclib().profiles())
        self.disableAutoRange()
        self.blockSignals(True)
        self.plotItem
        self.setViewportUpdateMode(QGraphicsView.NoViewportUpdate)
        self.updateProfileStyles(profiles) #take too much time
        self.updatePlot() #take much more time
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.blockSignals(False)
        self.enableAutoRange()
        self.viewport().update()



        s = ""

    def unitConversionFunction(self, unitSrc, unitDst):
        """
        Returns a function to convert a numeric value from unitSrc to unitDst.
        :param unitSrc: str, e.g. `micrometers` or `um` (case insensitive)
        :param unitDst: str, e.g. `nanometers` or `nm` (case insensitive)
        :return: callable, a function of pattern `mappedValues = func(value:list, pdi:SpectralProfilePlotDataItem)`
        """
        if isinstance(unitSrc, str):
            unitSrc = unitSrc.lower()
        if isinstance(unitDst, str):
            unitDst = unitDst.lower()

        key = (unitSrc, unitDst)
        func = self.mLUT_UnitConversions.get(key)
        if callable(func):
            return func
        else:
            if isinstance(unitSrc, str) and isinstance(unitDst, str) and convertMetricUnit(1, unitSrc,
                                                                                           unitDst) is not None:
                func = lambda values, pdi, a=unitSrc, b=unitDst: convertMetricUnit(values, a, b)
            else:
                func = lambda values, pdi: None

            self.mLUT_UnitConversions[key] = func

            return self.mLUT_UnitConversions[key]

    def setXUnit(self, unit: str):
        """
        Sets the unit or mapping function to be shown on x-axis.
        :param unit: str, e.g. `nanometers`
        """

        if self.mXUnit != unit:
            self.mViewBox.setXAxisUnit(unit)
            self.mXUnit = unit
            self.updateXUnit()

            self.getPlotItem().update()

    def xUnit(self) -> str:
        """
        Returns the unit to be shown on x-axis
        :return: str
        """
        return self.mXUnit

    def allPlotDataItems(self) -> list:
        """
        Returns all PlotDataItems (not only SpectralProfilePlotDataItems)
        :return: [list-of-PlotDataItems]
        """
        return list(self.mPlotDataItems.values()) + self.mPlotOverlayItems

    def allSpectralProfilePlotDataItems(self):
        """
        Returns alls SpectralProfilePlotDataItem, including those used as temporary overlays.
        :return: [list-of-SpectralProfilePlotDataItem]
        """
        return [pdi for pdi in self.allPlotDataItems() if isinstance(pdi, SpectralProfilePlotDataItem)]

    def updateXUnit(self):
        unit = self.xUnit()

        # update axis label
        self.setXLabel(unit)

        # update x values
        pdis = self.allSpectralProfilePlotDataItems()
        if unit == BAND_INDEX:
            func = lambda x, *args: list(range(len(x)))
            for pdi in pdis:
                pdi.setMapFunctionX(func)
                pdi.applyMapFunctions()
        else:
            for pdi in pdis:
                pdi.setMapFunctionX(self.unitConversionFunction(pdi.mInitialUnitX, unit))
                pdi.applyMapFunctions()

        s = ""

    def updatePlot(self):
        i = 0

        pi = self.getPlotItem()
        assert isinstance(pi, SpectralLibraryPlotItem)

        existing = list(self.mPlotDataItems.values())

        to_add = [i for i in existing if isinstance(i, SpectralProfilePlotDataItem) and i not in pi.dataItems]
        to_remove = [pdi for pdi in pi.dataItems if
                     isinstance(pdi, SpectralProfilePlotDataItem) and pdi not in existing]

        self._removeSpectralProfilePDIs(to_remove)
        pi.addItems(to_add)

        pi.update()
        s = ""

    def resetSpectralProfiles(self):
        for pdi in self.spectralProfilePlotDataItems():
            assert isinstance(pdi, SpectralProfilePlotDataItem)
            pdi.resetSpectralProfile()

    def spectralProfilePlotDataItems(self) -> list:
        """
        Returns all available SpectralProfilePlotDataItems
        """
        return [i for i in self.mPlotDataItems.values() if isinstance(i, SpectralProfilePlotDataItem)]

    def spectralProfilePlotDataItem(self, fid) -> SpectralProfilePlotDataItem:
        """
        Returns the SpectralProfilePlotDataItem related to SpectralProfile fid
        :param fid: int | QgsFeature | SpectralProfile
        :return: SpectralProfilePlotDataItem
        """
        if isinstance(fid, QgsFeature):
            fid = fid.id()
        return self.mPlotDataItems.get(fid)

    def updateProfileStyles(self, listOfProfiles: list):
        """
        Updates the styles for a set of SpectralProfilePlotDataItems
        :param listOfProfiles: [list-of-SpectralProfiles]
        """

        xUnit = None
        renderContext = QgsRenderContext()
        renderContext.setExtent(self.mSpeclib.extent())
        renderer = self.speclib().renderer().clone()
        colors = []

        from .spectrallibraries import DEFAULT_PROFILE_COLOR
        if isinstance(renderer, QgsNullSymbolRenderer):
            for i in range(len(listOfProfiles)):
                colors.append(DEFAULT_PROFILE_COLOR)
        else:

            renderer.startRender(renderContext, self.mSpeclib.fields())

            for profile in listOfProfiles:
                symbol = renderer.symbolForFeature(profile, renderContext)
                if not isinstance(symbol, QgsSymbol):
                    symbol = renderer.sourceSymbol()
                assert isinstance(symbol, QgsSymbol)
                color = QColor('white')

                if isinstance(symbol, (QgsMarkerSymbol, QgsLineSymbol, QgsFillSymbol)):
                    color = symbol.color()
                colors.append(color)
            renderer.stopRender(renderContext)

        s = ""
        for profile, color in zip(listOfProfiles, colors):
            assert isinstance(profile, SpectralProfile)

            if not self.mXUnitInitialized and isinstance(profile.xUnit(), str):
                self.setXUnit(profile.xUnit())

            id = profile.id()

            pdi = self.mPlotDataItems.get(id)
            if not isinstance(pdi, PlotDataItem):
                pdi = SpectralProfilePlotDataItem(profile)
                pdi.setClickable(True)
                pdi.sigClicked.connect(self.onProfileClicked)
                self.mPlotDataItems[profile.id()] = pdi
            pdi.setColor(color)


        if isinstance(xUnit, str):
            self.setXUnit(xUnit)
            self.mXUnitInitialized = True

    def onProfileClicked(self, pdi):
        if self.mUpdatesBlocked:
            return

        if isinstance(pdi, SpectralProfilePlotDataItem) and pdi in self.mPlotDataItems.values():
            modifiers = QApplication.keyboardModifiers()
            speclib = self.speclib()
            assert isinstance(speclib, SpectralLibrary)
            fid = pdi.id()

            fids = speclib.selectedFeatureIds()
            if modifiers == Qt.ShiftModifier:
                if fid in fids:
                    fids.remove(fid)
                else:
                    fids.append(fid)
                speclib.selectByIds(fids)
            else:
                speclib.selectByIds([fid])

    def setXLabel(self, label: str):
        """
        Sets the name of the X axis
        :param label: str, name
        """
        pi = self.getPlotItem()
        pi.getAxis('bottom').setLabel(label)

    def setYLabel(self, label: str):
        """
        Sets the name of the Y axis
        :param label: str, name
        """
        pi = self.getPlotItem()
        pi.getAxis('left').setLabel(label)

    def yLabel(self) -> str:
        return self.getPlotItem().getAxis('left').label

    def xLabel(self) -> str:
        return self.getPlotItem().getAxis('bottom').label

    def speclib(self) -> SpectralLibrary:
        """
        :return: SpectralLibrary
        """
        return self.mSpeclib

    def onProfilesAdded(self, fids):
        if not isinstance(fids, list):
            fids = [fids]
        if len(fids) == 0:
            return
        profiles = self.speclib().profiles(fids=fids)
        self.updateProfileStyles(list(profiles))
        self.updatePlot()
        s = ""

    def onProfilesRemoved(self, fids):
        if len(fids) == 0:
            return

        pi = self.getPlotItem()
        assert isinstance(pi, pg.PlotItem)
        to_remove = [pdi for pdi in self._spectralProfilePDIs() if pdi.id() in fids]
        self._removeSpectralProfilePDIs(to_remove)

    def dragEnterEvent(self, event):
        assert isinstance(event, QDragEnterEvent)
        if MIMEDATA_SPECLIB_LINK in event.mimeData().formats():
            event.accept()

    def dragMoveEvent(self, event):
        if MIMEDATA_SPECLIB_LINK in event.mimeData().formats():
            event.accept()


class SpectralViewBox(pg.ViewBox):
    """
    Subclass of ViewBox
    """
    sigXUnitChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        """
        Constructor of the CustomViewBox
        """
        super(SpectralViewBox, self).__init__(parent)
        # self.menu = None # Override pyqtgraph ViewBoxMenu
        # self.menu = self.getMenu() # Create the menu
        # self.menu = None

        xAction = [a for a in self.menu.actions() if a.text() == 'X Axis'][0]
        yAction = [a for a in self.menu.actions() if a.text() == 'Y Axis'][0]

        menuColors = self.menu.addMenu('Colors')
        frame = QFrame()
        l = QGridLayout()
        frame.setLayout(l)

        self.btnColorBackground = QgsColorButton(parent)
        self.btnColorForeground = QgsColorButton(parent)
        self.btnColorInfo = QgsColorButton(parent)
        self.btnColorSelected = QgsColorButton(parent)
        self.cbXAxisUnits = QComboBox(parent)

        def onBackgroundColorChanged(color: QColor):
            w = self._viewWidget()
            if isinstance(w, SpectralLibraryPlotWidget):
                w.setBackground(QColor(color))

        def onForegroundColorChanged(color: QColor):
            w = self._viewWidget()
            if isinstance(w, SpectralLibraryPlotWidget):
                w.setForegroundInfoColor(color)
                # w.setForegroundBrush(color)

        def onInfoColorChanged(color: QColor):
            w = self._viewWidget()
            if isinstance(w, SpectralLibraryPlotWidget):
                w.setInfoColor(color)
                s = ""

        self.btnColorBackground.colorChanged.connect(onBackgroundColorChanged)
        self.btnColorForeground.colorChanged.connect(onForegroundColorChanged)
        self.btnColorInfo.colorChanged.connect(onInfoColorChanged)

        l.addWidget(QLabel('Background'), 0, 0)
        l.addWidget(self.btnColorBackground, 0, 1)

        l.addWidget(QLabel('Foreground'), 1, 0)
        l.addWidget(self.btnColorForeground, 1, 1)

        l.addWidget(QLabel('Crosshair info'), 2, 0)
        l.addWidget(self.btnColorInfo, 2, 1)

        l.setMargin(1)
        l.setSpacing(1)
        frame.setMinimumSize(l.sizeHint())
        wa = QWidgetAction(menuColors)
        wa.setDefaultWidget(frame)
        menuColors.addAction(wa)

        menuXAxis = self.menu.addMenu('X Axis')

        # define the widget to set X-Axis options
        frame = QFrame()
        l = QGridLayout()
        frame.setLayout(l)
        self.rbXManualRange = QRadioButton('Manual')

        self.rbXAutoRange = QRadioButton('Auto')
        self.rbXAutoRange.setChecked(True)

        l.addWidget(self.rbXManualRange, 0, 0)
        l.addWidget(self.rbXAutoRange, 1, 0)

        self.mCBXAxisUnit = QComboBox()

        # Order of X units:
        # 1. long names
        # 2. short si names
        # 3. within these groups: by exponent
        items = sorted(METRIC_EXPONENTS.items(), key=lambda item: item[1])
        fullNames = []
        siNames = []
        for item in items:
            if len(item[0]) > 5:
                # make centimeters to Centimeters
                item = (item[0].title(), item[1])
                fullNames.append(item)
            else:
                siNames.append(item)

        self.mCBXAxisUnit.addItem(BAND_INDEX, userData='')
        for item in fullNames + siNames:
            name, exponent = item
            self.mCBXAxisUnit.addItem(name, userData=name)
        self.mCBXAxisUnit.setCurrentIndex(0)

        self.mCBXAxisUnit.currentIndexChanged.connect(
            lambda: self.sigXUnitChanged.emit(self.mCBXAxisUnit.currentText()))

        l.addWidget(QLabel('Unit'), 2, 0)
        l.addWidget(self.mCBXAxisUnit, 2, 1)

        self.mXAxisUnit = 'index'

        l.setMargin(1)
        l.setSpacing(1)
        frame.setMinimumSize(l.sizeHint())
        wa = QWidgetAction(menuXAxis)
        wa.setDefaultWidget(frame)
        menuXAxis.addAction(wa)

        self.menu.insertMenu(xAction, menuXAxis)
        self.menu.removeAction(xAction)

        self.mActionShowCrosshair = self.menu.addAction('Show Crosshair')
        self.mActionShowCrosshair.setCheckable(True)
        self.mActionShowCrosshair.setChecked(True)
        self.mActionShowCursorValues = self.menu.addAction('Show Mouse values')
        self.mActionShowCursorValues.setCheckable(True)
        self.mActionShowCursorValues.setChecked(True)

    def setXAxisUnit(self, unit: str):
        """
        Sets the X axis unit.
        :param unit: str, metric unit like `nm` or `Nanometers`.
        """
        i = self.mCBXAxisUnit.findText(unit)
        if i == -1:
            i = 0
        if i != self.mCBXAxisUnit.currentIndex():
            self.mCBXAxisUnit.setCurrentIndex(i)

    def xAxisUnit(self) -> str:
        """
        Returns unit of X-Axis values
        :return: str
        """
        return self.mCBXAxisUnit.currentText()

    def addItems(self, pdis: list, ignoreBounds=False):
        """
        Add multiple QGraphicsItem to this view. The view will include this item when determining how to set its range
        automatically unless *ignoreBounds* is True.
        """
        for i, item in enumerate(pdis):
            if item.zValue() < self.zValue():
                item.setZValue(self.zValue() + 1 + i)

        scene = self.scene()
        if scene is not None and scene is not item.scene():
            for item in pdis:
                scene.addItem(item)  ## Necessary due to Qt bug: https://bugreports.qt-project.org/browse/QTBUG-18616
                item.setParentItem(self.childGroup)
        if not ignoreBounds:
            self.addedItems.extend(pdis)
        # self.updateAutoRange()

    def updateContextMenu(self):

        w = self._viewWidget()
        if isinstance(w, SpectralLibraryPlotWidget):
            # get background color
            bg = w.backgroundBrush().color()
            self.btnColorBackground.setColor(bg)

            # get foreground color
            self.btnColorForeground.setColor(w.foregroundInfoColor())
            # get info color

            self.btnColorInfo.setColor(w.infoColor())

    def raiseContextMenu(self, ev):

        pt = self.mapDeviceToView(ev.pos())

        xRange, yRange = self.viewRange()

        menu = self.getMenu(ev)

        self.scene().addParentContextMenus(self, menu, ev)

        self.updateContextMenu()
        menu.exec_(ev.screenPos().toPoint())

    def updateCurrentPosition(self, x, y):
        self.mCurrentPosition = (x, y)
        pass

