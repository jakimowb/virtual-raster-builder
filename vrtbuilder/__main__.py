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


class run():
    # add site-packages to sys.path as done by enmapboxplugin.py

    from vrtbuilder.externals.qps.testing import start_app
    qgsApp = start_app()
    from vrtbuilder.widgets import VRTBuilderWidget
    W = VRTBuilderWidget(None)
    W.show()

    qgsApp.exec_()
    qgsApp.exitQgis()


if __name__ == '__main__':
    run()
