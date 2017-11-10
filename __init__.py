# -*- coding: utf-8 -*-
"""
/***************************************************************************
        VRT Builder Plugin
        This script initializes the plugin, making it known to QGIS.


                             -------------------
        begin                : 2017-08-20
        copyright            : (C) 2017 by HU-Berlin
        email                : benjamin.jakimow[at]geo.hu-berlin.de
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
# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load SenseCarbon_TSV class from file sensecarbon_tsv.py.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from vrtbuilderplugin import VRTBuilderPlugin
    return VRTBuilderPlugin(iface)
