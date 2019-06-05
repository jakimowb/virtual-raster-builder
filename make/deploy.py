# -*- coding: utf-8 -*-

"""
***************************************************************************
    deploy.py
    Script to build the VRT Raster Builder from Repository code
    ---------------------
    Date                 : June 2019
    Copyright            : (C) 2019 by Benjamin Jakimow
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



import os, sys, re, shutil, zipfile, datetime, requests, http, mimetypes
from requests.auth import HTTPBasicAuth
from http.client import responses
import xml.etree.ElementTree as ET
from xml.dom import minidom

import qgis.utils
from qgis.PyQt.QtCore import *
import numpy as np
from pb_tool import pb_tool
import git

from vrtbuilder.externals.qps.testing import initQgisApplication
app = initQgisApplication()
from vrtbuilder import DIR_REPO
from vrtbuilder.utils import file_search, jp, zipdir
import vrtbuilder


DIR_BUILD = jp(DIR_REPO, 'build')
DIR_DEPLOY = jp(DIR_REPO, 'deploy')
DIR_DOC_SOURCE = jp(DIR_REPO, *['doc','source'])

QGIS_MIN = '3.4'
QGIS_MAX = '3.99'
PATH_ABOUT_TEXT = jp(DIR_REPO, 'ABOUT_Plugin.html')
PATH_CHANGELOG = jp(DIR_REPO, 'CHANGELOG')

REPO = git.Repo(DIR_REPO)
currentBranch = REPO.active_branch.name



DIR_DEPLOY = jp(DIR_REPO, 'deploy')
pathCfg = jp(DIR_REPO, 'pb_tool.cfg')
CFG = pb_tool.get_config(pathCfg)
PLUGIN_FOLDER_NAME = CFG.get('plugin', 'name')

PLUGIN_REPO_XML_REMOTE = os.path.join(DIR_DEPLOY, 'qgis_plugin_develop.xml')
PLUGIN_REPO_XML_LOCAL  = os.path.join(DIR_DEPLOY, 'qgis_plugin_develop_local.xml')
URL_DOWNLOADS = r'https://bitbucket.org/jakimowb/eo-time-series-viewer/downloads'
urlDownloads = 'https://api.bitbucket.org/2.0/repositories/jakimowb/eo-time-series-viewer/downloads'


# list of deploy options:
# ZIP - add zipped plugin to DIR_DEPLOY
# UNZIPPED - add the non-zipped plugin to DIR_DEPLOY
DEPLOY_OPTIONS = ['ZIP', 'UNZIPPED']
ADD_TESTDATA = True


PLAIN_COPY_SUBDIRS = ['site-packages']

########## End of config section


REPO = git.Repo(DIR_REPO)
currentBranch = REPO.active_branch.name
timestamp = ''.join(np.datetime64(datetime.datetime.now()).astype(str).split(':')[0:-1]).replace('-','')
buildID = '{}.{}.{}'.format(re.search(r'(\.?[^.]*){2}', vrtbuilder.__version__).group()
                            , timestamp,
                            re.sub(r'[\\/]','_', currentBranch))


timestamp = ''.join(np.datetime64(datetime.datetime.now()).astype(str).split(':')[0:-1])
timestamp = re.sub('[-T]','', timestamp)

vrtbuilder.__version__ = buildID
dirBuildPlugin = jp(DIR_BUILD, PLUGIN_FOLDER_NAME)

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

class QGISMetadataFileWriter(object):

    def __init__(self):
        self.mName = None

        self.mDescription = None
        self.mVersion = None
        self.mQgisMinimumVersion = '3.4'
        self.mQgisMaximumVersion = '3.99'
        self.mAuthor = None
        self.mAbout = None
        self.mEmail = None
        self.mHomepage = None
        self.mIcon = None
        self.mTracker = None
        self.mRepository = None
        self.mIsExperimental = False
        self.mTags = None
        self.mCategory = None
        self.mChangelog = ''

    def validate(self)->bool:

        return True

    def metadataString(self)->str:
        assert self.validate()

        lines = ['[general]']
        lines.append('name={}'.format(self.mName))
        lines.append('author={}'.format(self.mAuthor))
        if self.mEmail:
            lines.append('email={}'.format(self.mEmail))

        lines.append('description={}'.format(self.mDescription))
        lines.append('version={}'.format(self.mVersion))
        lines.append('qgisMinimumVersion={}'.format(self.mQgisMinimumVersion))
        lines.append('qgisMaximumVersion={}'.format(self.mQgisMaximumVersion))
        lines.append('about={}'.format(re.sub('\n', '', self.mAbout)))

        lines.append('icon={}'.format(self.mIcon))

        lines.append('tags={}'.format(', '.join(self.mTags)))
        lines.append('category={}'.format(self.mRepository))

        lines.append('homepage={}'.format(self.mHomepage))
        if self.mTracker:
            lines.append('tracker={}'.format(self.mTracker))
        if self.mRepository:
            lines.append('repository={}'.format(self.mRepository))
        if isinstance(self.mIsExperimental, bool):
            lines.append('experimental={}'.format(self.mIsExperimental))


        #lines.append('deprecated={}'.format(self.mIsDeprecated))
        lines.append('')
        lines.append('changelog={}'.format(self.mChangelog))

        return '\n'.join(lines)
    """
    [general]
    name=dummy
    description=dummy
    version=dummy
    qgisMinimumVersion=dummy
    qgisMaximumVersion=dummy
    author=dummy
    about=dummy
    email=dummy
    icon=dummy
    homepage=dummy
    tracker=dummy
    repository=dummy
    experimental=False
    deprecated=False
    tags=remote sensing, raster, time series, data cube, landsat, sentinel
    category=Raster
    """

    def writeMetadataTxt(self, path:str):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.metadataString())
        # read again and run checks
        import pyplugin_installer.installer_data

        # test if we could read the plugin
        import pyplugin_installer.installer_data
        P = pyplugin_installer.installer_data.Plugins()
        plugin = P.getInstalledPlugin(self.mName, os.path.dirname(path), True)

        #if hasattr(pyplugin_installer.installer_data, 'errorDetails'):
        #    raise Exception('plugin structure/metadata error:\n{}'.format(pyplugin_installer.installer_data.errorDetails))
        s = ""




def build():

    # local pb_tool configuration file.
    pathCfg = jp(DIR_REPO, 'pb_tool.cfg')
    cfg = pb_tool.get_config(pathCfg)
    cdir = os.path.dirname(pathCfg)
    pluginname = cfg.get('plugin', 'name')
    dirPlugin = jp(DIR_DEPLOY, pluginname)
    os.chdir(cdir)

    mkDir(DIR_DEPLOY)

    # describe metadata
    import vrtbuilder
    MD = QGISMetadataFileWriter()
    #with open(PATH_ABOUT_TEXT, 'r', encoding='utf-8') as f:
    #    aboutText = f.readlines()
    #    for i in range(1, len(aboutText)):
    #        aboutText[i] = '    ' + aboutText[i]
    #    aboutText = ''.join(aboutText)

    with open(PATH_CHANGELOG, 'r', encoding='utf-8') as f:
        changelog = f.readlines()
        changelog = ''.join(changelog)
    MD.mChangelog = changelog

    MD.mName = vrtbuilder.TITLE
    MD.mCategory = 'Raster'
    MD.mAbout = vrtbuilder.ABOUT
    MD.mDescription = vrtbuilder.DESCRIPTION
    MD.mVersion = buildID
    MD.mTracker = vrtbuilder.ISSUE_TRACKER
    MD.mHomepage = vrtbuilder.HOMEPAGE
    MD.mRepository = vrtbuilder.REPOSITORY
    MD.mQgisMinimumVersion = QGIS_MIN
    MD.mQgisMaximumVersion = QGIS_MAX
    MD.mAuthor = vrtbuilder.AUTHOR
    MD.mEmail = vrtbuilder.MAIL
    MD.mIcon = 'vrtbuilder/icon.png'
    MD.mTags = ['remote sensing', 'raster', 'landsat', 'sentinel']
    print(MD.metadataString())


    if os.path.isdir(dirPlugin):
        print('Remove old build folder...')
        shutil.rmtree(dirPlugin, ignore_errors=True)

    # required to choose andy DIR_DEPLOY of choice
    # issue tracker: https://github.com/g-sherman/plugin_build_tool/issues/4

    if True:
        # 1. clean an existing directory = plugin folder
        pb_tool.clean_deployment(ask_first=False)

        import make
        make.compileResourceFiles()

        # 3. Deploy = write the data to the new plugin folder
        pb_tool.deploy_files(pathCfg, DIR_DEPLOY, quick=True, confirm=False)

        # 4. As long as we can not specify in the pb_tool.cfg which file types are not to deploy,
        # we need to remove them afterwards.
        # issue: https://github.com/g-sherman/plugin_build_tool/issues/5
        print('Remove files...')

        if True:
            # delete help folder
            shutil.rmtree(os.path.join(dirPlugin, *['help']), ignore_errors=True)
        for f in file_search(DIR_DEPLOY, re.compile('(svg|pyc)$'), recursive=True):
            os.remove(f)
        for d in file_search(DIR_DEPLOY, '__pycache__', directories=True, recursive=True):
            os.rmdir(d)


    # update metadata version
    if True:
        pathMetadata = jp(dirPlugin, 'metadata.txt')

        MD.writeMetadataTxt(pathMetadata)

        # update version number in metadata

        pathPackageInit = jp(dirPlugin, *['vrtbuilder', '__init__.py'])
        f = open(pathPackageInit)
        lines = f.read()
        f.close()
        lines = re.sub(r'(__version__\W*=\W*)([^\n]+)', r'__version__ = "{}"\n'.format(buildID), lines)
        f = open(pathPackageInit, 'w')
        f.write(lines)
        f.flush()
        f.close()

    # copy CHANGELOG to doc/source/changelog.rst
    updateSphinxChangelog()

    # 5. create a zip
    print('Create zipfile...')


    pluginname = cfg.get('plugin', 'name')
    pathZip = jp(DIR_DEPLOY, '{}.{}.zip'.format(pluginname, buildID))
    dirPlugin = jp(DIR_DEPLOY, pluginname)
    zipdir(dirPlugin, pathZip)
    # os.chdir(dirPlugin)
    # shutil.make_archive(pathZip, 'zip', '..', dirPlugin)

    # 6. Update XML repositories
    updateRepositoryXML(MD, path=pathZip)

    # 6. install the zip file into the local QGIS instance. You will need to restart QGIS!
    if True:
        print('\n### To update/install the {} plugin run this command on your QGIS Python shell:\n'.format(vrtbuilder.TITLE))
        print('from pyplugin_installer.installer import pluginInstaller')
        print('pluginInstaller.installFromZipFile(r"{}")'.format(pathZip))
        print('#### Close (and restart manually)\n')
        #print('iface.mainWindow().close()\n')
        print('QProcess.startDetached(QgsApplication.arguments()[0], [])')
        print('QgsApplication.quit()\n')
        print('## press ENTER\n')

    print('Finished')

def updateSphinxChangelog():
    from vrtbuilder import PATH_CHANGELOG
    with open(PATH_CHANGELOG, 'r') as f:
        # replace (#1) with (https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/1)
        urlPrefix = r'https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/'
        lines = f.readlines()
        lines = [re.sub(r'(#(\d+))', r'`#\2 <{}\2>`_'.format(urlPrefix), line) for line in lines]

        pathChangelogRst = jp(DIR_DOC_SOURCE, 'changelog.rst')

        with open(pathChangelogRst, 'w', encoding='utf-8') as f2:
            f2.writelines(lines)

        s = ""



def updateRepositoryXML(MD:QGISMetadataFileWriter, path:str=None):
    """
    Creates the XML files:
        deploy/qgis_plugin_develop.xml - to be uploaded to the bitbucket repository
        deploy/qgis_plugin_develop_local.xml - can be used as local QGIS Repository source
    :param path: str, optional, path of local *.zip which has been build with build()
    :return:
    """
    if not isinstance(path, str):
        zipFiles = list(file_search(DIR_DEPLOY, '*eotimeseriesviewer*.zip'))
        zipFiles.sort(key=lambda f:os.path.getctime(f))
        path = zipFiles[-1]

    assert isinstance(MD, QGISMetadataFileWriter)
    assert isinstance(path, str)
    assert os.path.isfile(path)
    assert os.path.splitext(path)[1] == '.zip'

    os.makedirs(DIR_DEPLOY, exist_ok=True)
    bn = os.path.basename(path)
    version = re.search(r'^'+PLUGIN_FOLDER_NAME+'\.(.*)\.zip$', bn).group(1)
    s = ""
    """
 <?xml-stylesheet type="text/xsl" href="plugins.xsl" ?>
<plugins>
   <pyqgis_plugin name="" version="">
        <description></description>
        <about></about>
        <version></version>
        <trusted>True</trusted>
        <qgis_minimum_version>dummy</qgis_minimum_version>
        <qgis_maximum_version>dummy</qgis_maximum_version>
        <homepage></homepage>
        <file_name></file_name>
        <icon></icon>
        <author_name></author_name>
        <download_url></download_url>
        <uploaded_by></uploaded_by>
        <experimental>False</experimental>
        <deprecated>False</deprecated>
        <tracker></tracker>
        <repository></repository>
        <tags></tags>
        <downloads>0</downloads>
        <average_vote>0.0</average_vote>
        <rating_votes>0</rating_votes>
        <external_dependencies></external_dependencies>
        <server>True</server>
    </pyqgis_plugin>
</plugins>
    """
    download_url = URL_DOWNLOADS+'/'+bn

    root = ET.Element('plugins')
    plugin = ET.SubElement(root, 'pyqgis_plugin')
    plugin.attrib['name'] = "{} (develop version)".format(MD.mName)
    plugin.attrib['version'] = '{}'.format(MD.mVersion)
    ET.SubElement(plugin, 'description').text = MD.mDescription
    ET.SubElement(plugin, 'about').text = MD.mAbout
    ET.SubElement(plugin, 'version').text = MD.mVersion
    ET.SubElement(plugin, 'qgis_minimum_version').text = MD.mQgisMinimumVersion
    ET.SubElement(plugin, 'qgis_maximum_version').text = MD.mQgisMaximumVersion
    ET.SubElement(plugin, 'homepage').text = MD.mHomepage
    ET.SubElement(plugin, 'file_name').text = bn
    ET.SubElement(plugin, 'icon').text = 'icon.svg'
    ET.SubElement(plugin, 'author_name').text = MD.mAuthor
    ET.SubElement(plugin, 'download_url').text = download_url
    ET.SubElement(plugin, 'deprecated').text = 'False'

    ET.SubElement(plugin, 'tracker').text = MD.mTracker
    ET.SubElement(plugin, 'repository').text = MD.mRepository
    ET.SubElement(plugin, 'tags').text = ', '.join(MD.mTags)
    ET.SubElement(plugin, 'experimental').text = 'False'

    tree = ET.ElementTree(root)

    xml = ET.tostring(root)
    dom = minidom.parseString(xml)
    #<?xml version="1.0"?>
    #<?xml-stylesheet type="text/xsl" href="plugins.xsl" ?>
    #pi1 = dom.createProcessingInstruction('xml', 'version="1.0"')
    url_xsl = 'https://plugins.qgis.org/static/style/plugins.xsl'
    pi2 = dom.createProcessingInstruction('xml-stylesheet', 'type="text/xsl" href="{}"'.format(url_xsl))

    dom.insertBefore(pi2, dom.firstChild)

    xmlRemote = dom.toprettyxml(encoding='utf-8').decode('utf-8')

    with open(PLUGIN_REPO_XML_REMOTE, 'w') as f:
        f.write(xmlRemote)

    import pathlib
    uri = pathlib.Path(path).as_uri()
    xmlLocal = re.sub(r'<download_url>.*</download_url>', r'<download_url>{}</download_url>'.format(uri), xmlRemote)
    with open(PLUGIN_REPO_XML_LOCAL, 'w') as f:
        f.write(xmlLocal)


if __name__ == "__main__":
    #updateSphinxChangelog()
    build()