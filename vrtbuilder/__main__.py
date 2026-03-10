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


def run():
    # add site-packages to sys.path as done by enmapboxplugin.py

    from vrtbuilder.qgispluginsupport.qps.testing import start_app
    qgs_app = start_app()
    from vrtbuilder.widgets import VRTBuilderWidget
    w = VRTBuilderWidget(None)
    w.show()

    qgs_app.exec_()
    qgs_app.exitQgis()


if __name__ == '__main__':
    run()
