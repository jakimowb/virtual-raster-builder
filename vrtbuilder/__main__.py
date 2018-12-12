# -*- coding: utf-8 -*-

"""
***************************************************************************
    __main__
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
import os

from vrtbuilder import DIR_EXAMPLEDATA
from vrtbuilder.utils import file_search


class run():

    # add site-packages to sys.path as done by enmapboxplugin.py

    from vrtbuilder.utils import initQgisApplication
    qgsApp = initQgisApplication()
    from vrtbuilder.widgets import VRTBuilderWidget
    W = VRTBuilderWidget(None)
    from exampledata import landsat1, landsat2, landsat2_SAD, rapideye_west
    W.addSourceFile(landsat1)
    W.addSourceFile(landsat2)
    W.addSourceFile(landsat2_SAD)
    W.addSourceFile(rapideye_west)
    W.show()

    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()

if __name__ == '__main__':
    run()