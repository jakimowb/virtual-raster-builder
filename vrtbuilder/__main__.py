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
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

class run():

    # add site-packages to sys.path as done by enmapboxplugin.py

    from utils import initQgisEnvironment
    qgsApp = initQgisEnvironment()
    from vrtbuilder.widgets import
    S = TimeSeriesViewer(None)
    S.ui.show()
    S.run()

    #close QGIS
    qgsApp.exec_()
    qgsApp.exitQgis()

if __name__ == '__main__':
    from timeseriesviewer.main import __main__
    __main__()
