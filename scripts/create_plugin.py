# -*- coding: utf-8 -*-

"""
***************************************************************************
    create_plugin.py
    Script to build the VRT Builder Plugin from Repository code
    ---------------------
    Date                 : August 2020
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.
                 *
*                                                                         *
***************************************************************************
"""
# noinspection PyPep8Naming

import argparse
import datetime
import os
import pathlib
import re
import requests
import shutil
import sys
import typing
import io
import site
import xml.etree.ElementTree as ET
from xml.dom import minidom
from http.client import responses
DIR_REPO = pathlib.Path(__file__).parents[1]
site.addsitedir(DIR_REPO)

import vrtbuilder
from vrtbuilder import DIR_REPO, __version__
from vrtbuilder.externals.qps.make.deploy import QGISMetadataFileWriter
from vrtbuilder.externals.qps.utils import file_search, zipdir
from requests.auth import HTTPBasicAuth

from qgis.PyQt.QtCore import *

CHECK_COMMITS = False

########## Config Section

MD = QGISMetadataFileWriter()
MD.mName = 'Virtual Raster Builder'
MD.mDescription = 'A QGIS Plugin to create GDAL Virtual Raster (VRT) files by drag and drop.'
MD.mTags = ['Raster', 'VRT', 'Virtual Raster', 'GDAL']
MD.mCategory = 'Analysis'
MD.mAuthor = 'Benjamin Jakimow, Geomatics Lab, Humboldt-Universität zu Berlin'
MD.mIcon = 'vrtbuilder/icon.png'
MD.mHomepage = vrtbuilder.URL_HOMEPAGE
MD.mAbout = vrtbuilder.ABOUT
MD.mTracker = vrtbuilder.URL_ISSUETRACKER
MD.mRepository = vrtbuilder.URL_REPOSITORY
MD.mQgisMinimumVersion = '3.14'
MD.mEmail = 'benjamin.jakimow@geo.hu-berlin.de'

PLUGIN_DIR_NAME = 'vrtbuilderplugin'


########## End of config section

def scantree(path, pattern=re.compile('.$')) -> typing.Iterator[pathlib.Path]:
    """
    Recursively returns file paths in directory
    :param path: root directory to search in
    :param pattern: str with required file ending, e.g. ".py" to search for *.py files
    :return: pathlib.Path
    """
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            yield from scantree(entry.path, pattern=pattern)
        elif entry.is_file and pattern.search(entry.path):
            yield pathlib.Path(entry.path)


def create_plugin(include_testdata: bool = False, include_qgisresources: bool = False):
    DIR_REPO = pathlib.Path(__file__).resolve().parents[1]
    assert (DIR_REPO / '.git').is_dir()

    DIR_DEPLOY = DIR_REPO / 'deploy'

    try:
        import git
        REPO = git.Repo(DIR_REPO)
        currentBranch = REPO.active_branch.name
    except Exception as ex:
        currentBranch = 'TEST'
        print('Unable to find git repo. Set currentBranch to "{}"'.format(currentBranch))

    timestamp = datetime.datetime.now().isoformat().split('.')[0]

    BUILD_NAME = '{}.{}.{}'.format(__version__, timestamp, currentBranch)
    BUILD_NAME = re.sub(r'[:-]', '', BUILD_NAME)
    BUILD_NAME = re.sub(r'[\\/]', '_', BUILD_NAME)
    PLUGIN_DIR = DIR_DEPLOY / PLUGIN_DIR_NAME
    PLUGIN_ZIP = DIR_DEPLOY / f'{PLUGIN_DIR_NAME}.{BUILD_NAME}.zip'

    if PLUGIN_DIR.is_dir():
        shutil.rmtree(PLUGIN_DIR)
    os.makedirs(PLUGIN_DIR, exist_ok=True)

    PATH_METADATAFILE = PLUGIN_DIR / 'metadata.txt'
    MD.mVersion = BUILD_NAME
    MD.writeMetadataTxt(PATH_METADATAFILE)

    # 1. (re)-compile all enmapbox resource files

    from scripts.compile_resourcefiles import compileVRTBuilderResources
    compileVRTBuilderResources()

    # copy python and other resource files
    pattern = re.compile(r'\.(py|svg|png|txt|ui|tif|qml|md|js|css)$')
    files = list(scantree(DIR_REPO / 'vrtbuilder', pattern=pattern))
    files.append(DIR_REPO / '__init__.py')
    files.append(DIR_REPO / 'CHANGELOG.rst')
    files.append(DIR_REPO / 'LICENSE.md')
    files.append(DIR_REPO / 'LICENSE.txt')
    files.append(DIR_REPO / 'requirements.txt')
    files.append(DIR_REPO / 'requirements-dev.txt')

    for fileSrc in files:
        assert fileSrc.is_file()
        fileDst = PLUGIN_DIR / fileSrc.relative_to(DIR_REPO)
        os.makedirs(fileDst.parent, exist_ok=True)
        shutil.copy(fileSrc, fileDst.parent)

    # update metadata version

    f = open(DIR_REPO / 'vrtbuilder' / '__init__.py')
    lines = f.read()
    f.close()
    lines = re.sub(r'(__version__\W*=\W*)([^\n]+)', r'__version__ = "{}"\n'.format(BUILD_NAME), lines)
    f = open(PLUGIN_DIR / 'vrtbuilder' / '__init__.py', 'w')
    f.write(lines)
    f.flush()
    f.close()

    # include test data into test versions
    if include_testdata and not re.search(currentBranch, 'master', re.I):
        if os.path.isdir(vrtbuilder.DIR_EXAMPLEDATA):
            shutil.copytree(vrtbuilder.DIR_EXAMPLEDATA, PLUGIN_DIR / 'exampledata')

    if include_qgisresources and not re.search(currentBranch, 'master', re.I):
        qgisresources = pathlib.Path(DIR_REPO) / 'qgisresources'
        shutil.copytree(qgisresources, PLUGIN_DIR / 'qgisresources')

    createCHANGELOG(PLUGIN_DIR)

    # 5. create a zip
    print('Create zipfile...')
    zipdir(PLUGIN_DIR, PLUGIN_ZIP)

    # 7. install the zip file into the local QGIS instance. You will need to restart QGIS!
    if True:
        info = []
        info.append('\n### To update/install the EnMAP-Box, run this command on your QGIS Python shell:\n')
        info.append('from pyplugin_installer.installer import pluginInstaller')
        info.append('pluginInstaller.installFromZipFile(r"{}")'.format(PLUGIN_ZIP))
        info.append('#### Close (and restart manually)\n')
        # print('iface.mainWindow().close()\n')
        info.append('QProcess.startDetached(QgsApplication.arguments()[0], [])')
        info.append('QgsApplication.quit()\n')
        info.append('## press ENTER\n')

        print('\n'.join(info))

        # cb = QGuiApplication.clipboard()
        # if isinstance(cb, QClipboard):
        #    cb.setText('\n'.join(info))

    print('Finished')


def createCHANGELOG(dirPlugin):
    """
    Reads the CHANGELOG.rst and creates the deploy/CHANGELOG (without extension!) for the QGIS Plugin Manager
    :return:
    """

    pathMD = os.path.join(DIR_REPO, 'CHANGELOG.rst')
    pathCL = os.path.join(dirPlugin, 'CHANGELOG')

    os.makedirs(os.path.dirname(pathCL), exist_ok=True)
    assert os.path.isfile(pathMD)
    import docutils.core

    overrides = {'stylesheet': None,
                 'embed_stylesheet': False,
                 'output_encoding': 'utf-8',
                 }
    buffer = io.StringIO()
    html = docutils.core.publish_file(
        source_path=pathMD,
        writer_name='html5',
        destination=buffer,
        settings_overrides=overrides)

    xml = minidom.parseString(html)
    #  remove headline
    for i, node in enumerate(xml.getElementsByTagName('h1')):
        if i == 0:
            node.parentNode.removeChild(node)
        else:
            node.tagName = 'h4'

    for node in xml.getElementsByTagName('link'):
        node.parentNode.removeChild(node)

    for node in xml.getElementsByTagName('meta'):
        if node.getAttribute('name') == 'generator':
            node.parentNode.removeChild(node)

    xml = xml.getElementsByTagName('body')[0]
    html = xml.toxml()
    html_cleaned = []
    for line in html.split('\n'):
        # line to modify
        line = re.sub(r'class="[^"]*"', '', line)
        line = re.sub(r'id="[^"]*"', '', line)
        line = re.sub(r'<li><p>', '<li>', line)
        line = re.sub(r'</p></li>', '</li>', line)
        line = re.sub(r'</?(dd|dt|div|body)[ ]*>', '', line)
        line = line.strip()
        if line != '':
            html_cleaned.append(line)
    # make html compact

    with open(pathCL, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html_cleaned))

    if False:
        with open(pathCL + '.html', 'w', encoding='utf-8') as f:
            f.write('\n'.join(html_cleaned))
    s = ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Install exampledata')
    parser.add_argument('-t', '--testdata',
                        required=False,
                        default=False,
                        help='Add exampledata directory to plugin zip',
                        action='store_true')
    parser.add_argument('-q', '--qgisresources',
                        required=False,
                        default=False,
                        help='Add qgisresources directory to plugin zip. This is only required for test environments',
                        action='store_true')

    args = parser.parse_args()

    create_plugin(include_testdata=args.testdata, include_qgisresources=args.qgisresources)
    exit()
