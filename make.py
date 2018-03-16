# -*- coding: utf-8 -*-

"""
***************************************************************************
    make.py
    Purpose: resource generation and plugin deployment
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
import os, sys, six, subprocess, re, shutil

from pb_tool import pb_tool
import datetime
import numpy as np

from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

from PyQt5.QtSvg import *
from PyQt5.QtXml import *


import vrtbuilder
from vrtbuilder import DIR_UI, DIR_ROOT
from vrtbuilder.utils import file_search
jp = os.path.join

DIR_BUILD = jp(DIR_ROOT, 'build')
DIR_DEPLOY = jp(DIR_ROOT, 'deploy')


def getDOMAttributes(elem):
    assert isinstance(elem, QDomElement)
    values = dict()
    attributes = elem.attributes()
    for a in range(attributes.count()):
        attr = attributes.item(a)
        values[str(attr.nodeName())] = attr.nodeValue()
    return values


def compile_rc_files(ROOT):
    #find ui files
    ui_files = file_search(ROOT, '*.ui', recursive=True)
    qrcs = set()

    doc = QDomDocument()
    reg = re.compile('(?<=resource=")[^"]+\.qrc(?=")')

    for ui_file in ui_files:
        pathDir = os.path.dirname(ui_file)
        doc.setContent(QFile(ui_file))
        includeNodes = doc.elementsByTagName('include')
        for i in range(includeNodes.count()):
            attr = getDOMAttributes(includeNodes.item(i).toElement())
            if 'location' in attr.keys():
                print((ui_file, str(attr['location'])))
                qrcs.add((pathDir, str(attr['location'])))

    #compile Qt resource files
    #resourcefiles = file_search(ROOT, '*.qrc', recursive=True)
    resourcefiles = list(qrcs)
    assert len(resourcefiles) > 0

    if sys.platform == 'darwin':
        prefix = '/Applications/QGIS.app/Contents/MacOS/bin/'
    else:
        prefix = ''



    for root_dir, f in resourcefiles:
        #dn = os.path.dirname(f)
        pathQrc = os.path.normpath(jp(root_dir, f))
        assert os.path.exists(pathQrc), pathQrc
        bn = os.path.basename(f)
        bn = os.path.splitext(bn)[0]
        pathPy2 = os.path.join(DIR_UI, bn+'.py' )
        pathRCC = os.path.join(DIR_UI, bn+'.rcc' )
        subprocess.call(['pyrcc5', '-py3', '-o', pathPy2, pathQrc])
        s = ""

def fileNeedsUpdate(file1, file2):
    if not os.path.exists(file2):
        return True
    else:
        if not os.path.exists(file1):
            return True
        else:
            return os.path.getmtime(file1) > os.path.getmtime(file2)



def updateMetadataTxt():
    #see http://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/plugins.html#plugin-metadata
    #for required & optional meta tags
    pathDst = jp(DIR_ROOT, 'metadata.txt')
    pathChanges = jp(DIR_ROOT, 'CHANGES.txt' )
    assert os.path.exists(pathDst)

    import collections
    md = collections.OrderedDict()
    for line in open(pathDst).readlines():
        parts = line.split('=')
        if len(parts) >= 2:
            md[parts[0]] = '='.join(parts[1:])





    #update/set new metadata
    import vrtbuilder
    md['name'] = vrtbuilder.TITLE
    md['qgisMinimumVersion'] = "3.0"
    #md['qgisMaximumVersion'] =
    md['description'] = vrtbuilder.DESCRIPTION.strip()
    md['about'] = '\n\t'.join(vrtbuilder.ABOUT.splitlines())
    md['version'] = vrtbuilder.VERSION.strip()
    md['author'] = "Benjamin Jakimow, Geomatics Lab, Humboldt-Universität zu Berlin"
    md['email'] = "benjamin.jakimow@geo.hu-berlin.de"

    f = open(pathChanges)
    lines = f.readlines()
    f.close()

    md['changelog'] = ''.join(lines)
    md['experimental'] = "False"
    md['deprecated'] = "False"
    md['tags'] = "remote sensing, raster"
    md['homepage'] = vrtbuilder.WEBSITE
    md['repository'] = vrtbuilder.WEBSITE
    md['tracker'] = vrtbuilder.WEBSITE+'/issues'
    md['icon'] = 'vrtbuilder/icon.png'
    md['category'] = 'Raster'

    lines = ['[general]']
    for k, line in md.items():
        lines.append('{}={}'.format(k, line))
    f = open(pathDst, 'w', encoding='utf-8')
    f.writelines('\n'.join(lines))
    f.flush()
    f.close()

    s = ""

def make_pb_tool_cfg():
    pathPBToolCgf = r''

    lines = open(pathPBToolCgf).readlines()

    #main_dialog:


def mkDir(d, delete=False):
    """
    Make directory.
    :param d: path of directory to be created
    :param delete: set on True to delete the directory contents, in case the directory already existed.
    """
    if delete and os.path.isdir(d):
        cleanDir(d)
    if not os.path.isdir(d):
        os.makedirs(d)


def rm(p):
    """
    Remove files or directory 'p'
    :param p: path of file or directory to be removed.
    """
    if os.path.isfile(p):
        os.remove(p)
    elif os.path.isdir(p):
        shutil.rmtree(p)

def cleanDir(d):
    """
    Remove content from directory 'd'
    :param d: directory to be cleaned.
    """
    assert os.path.isdir(d)
    for root, dirs, files in os.walk(d):
        for p in dirs + files: rm(jp(root,p))
        break

def deploy():
    timestamp = ''.join(np.datetime64(datetime.datetime.now()).astype(str).split(':')[0:-1])
    buildID = '{}.{}'.format(vrtbuilder.VERSION, timestamp)
    dirBuildPlugin = jp(DIR_BUILD, 'vrtbuilderplugin')

    #the directory to build the "enmapboxplugin" folder

    DIR_DEPLOY = jp(DIR_ROOT, 'deploy')
    #DIR_DEPLOY = r'E:\_EnMAP\temp\temp_bj\enmapbox_deploys\most_recent_version'
    os.chdir(DIR_ROOT)
    #local pb_tool configuration file.
    pathCfg = jp(DIR_ROOT, 'pb_tool.cfg')

    mkDir(DIR_DEPLOY)

    #required to choose andy DIR_DEPLOY of choice
    #issue tracker: https://github.com/g-sherman/plugin_build_tool/issues/4
    pb_tool.get_plugin_directory = lambda : DIR_DEPLOY
    cfg = pb_tool.get_config(config=pathCfg)

    if True:
        #1. clean an existing directory = the enmapboxplugin folder
        pb_tool.clean_deployment(ask_first=False, config=pathCfg)

        #2. Compile. Basically call pyrcc to create the resources.rc file
        #I don't know how to call this from pure python

        cfgParser = pb_tool.get_config(config=pathCfg)
        pb_tool.compile_files(cfgParser)

        #3. Deploy = write the data to the new enmapboxplugin folder
        pb_tool.deploy_files(pathCfg, DIR_DEPLOY, confirm=False, quick=True)

        #4. As long as we can not specify in the pb_tool.cfg which file types are not to deploy,
        # we need to remove them afterwards.
        # issue: https://github.com/g-sherman/plugin_build_tool/issues/5
        print('Remove files...')

        for f in file_search(DIR_DEPLOY, re.compile('(svg|pyc)$'), recursive=True):
            os.remove(f)

    #5. create a zip
    print('Create zipfile...')
    from vrtbuilder.utils import zipdir

    pluginname= cfg.get('plugin', 'name')
    pathZip = jp(DIR_DEPLOY, '{}.{}.zip'.format(pluginname,timestamp))
    dirPlugin = jp(DIR_DEPLOY, pluginname)
    zipdir(dirPlugin, pathZip)
    #os.chdir(dirPlugin)
    #shutil.make_archive(pathZip, 'zip', '..', dirPlugin)

    #6. copy to local QGIS user DIR
    if True:
        import shutil

        from os.path import expanduser
        #QGIS 2 pathQGIS = os.path.join(expanduser("~"), *['.qgis2','python','plugins'])

        from vrtbuilder.utils import initQgisApplication
        qgsApp = initQgisApplication()

        import qgis.user

        pathQGIS = qgis.user.userpythonhome
        pathQGIS = pathQGIS.replace('python3', 'QGIS/QGIS3')
        pathQGIS = os.path.join(pathQGIS, *['plugins'])



        assert os.path.isdir(pathQGIS)
        pathDst = os.path.join(pathQGIS, os.path.basename(dirPlugin))
        rm(pathDst)
        shutil.copytree(dirPlugin, pathDst)
        s  =""


    print('Finished')



if __name__ == '__main__':
    icondir = jp(DIR_UI)
    pathQrc = jp(DIR_UI,'resources.qrc')


    if True:
        updateMetadataTxt()
        #updateHelpHTML()
        #exit()
    if False:
        compile_rc_files(DIR_UI)

    if True:
        deploy()
    print('Done')

