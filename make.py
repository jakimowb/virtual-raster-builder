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

import pb_tool
import datetime
import numpy as np

from qgis import *
from qgis.core import *
from qgis.gui import *
import six
if six.PY3:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtSvg import *
    from PyQt5.QtXml import *
else:
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *
    from PyQt4.QtSvg import *
    from PyQt4.QtXml import *

import gdal

#import vrtbuilder
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
        pathPy = os.path.join(DIR_UI, bn+'.py' )
        pathRCC = os.path.join(DIR_UI, bn+'.rcc' )
        if six.PY3:
            #subprocess.call(['pyrcc5', '-o', pathPy, pathQrc])
            subprocess.call(['pyrcc4', '-py"', '-o', pathPy, pathQrc])
            lines = open(pathPy, 'r').readlines()
            lines = [l.replace('PyQt4', 'PyQt5') for l in lines]
            open(pathPy, 'w').writelines(lines)
            s =  ""
        else:
            subprocess.call(['pyrcc4', '-py"', '-o', pathPy, pathQrc])
            lines = open(pathPy, 'r').readlines()
            lines = [l.replace('PyQt4','PyQt5') for l in lines]
            open(pathPy, 'w').writelines(lines)
        s = ""

def fileNeedsUpdate(file1, file2):
    if not os.path.exists(file2):
        return True
    else:
        if not os.path.exists(file1):
            return True
        else:
            return os.path.getmtime(file1) > os.path.getmtime(file2)

def svg2png(pathDir, overwrite=False, mode='INKSCAPE'):
    assert mode in ['INKSCAPE', 'WEBKIT', 'SVG']
    from PyQt5.QtWebKit import QWebPage

    svgs = file_search(pathDir, '*.svg')
    app = QApplication([], True)
    buggySvg = []


    for pathSvg in svgs:
        dn = os.path.dirname(pathSvg)
        bn, _ = os.path.splitext(os.path.basename(pathSvg))
        pathPng = jp(dn, bn+'.png')

        if mode == 'SVG':
            renderer = QSvgRenderer(pathSvg)
            doc_size = renderer.defaultSize() # size in px
            img = QImage(doc_size, QImage.Format_ARGB32)
            #img.fill(0xaaA08080)
            painter = QPainter(img)
            renderer.render(painter)
            painter.end()
            if overwrite or not os.path.exists(pathPng):
                img.save(pathPng, quality=100)
            del painter, renderer
        elif mode == 'WEBKIT':
            page = QWebPage()
            frame = page.mainFrame()
            f = QFile(pathSvg)
            if f.open(QFile.ReadOnly | QFile.Text):
                textStream = QTextStream(f)
                svgData = textStream.readAll()
                f.close()

            qba = QByteArray(str(svgData))
            frame.setContent(qba,"image/svg+xml")
            page.setViewportSize(frame.contentsSize())

            palette = page.palette()
            background_color = QColor(50,0,0,50)
            palette.setColor(QPalette.Window, background_color)
            brush = QBrush(background_color)
            palette.setBrush(QPalette.Window, brush)
            page.setPalette(palette)

            img = QImage(page.viewportSize(), QImage.Format_ARGB32)
            img.fill(background_color) #set transparent background
            painter = QPainter(img)
            painter.setBackgroundMode(Qt.OpaqueMode)
            #print(frame.renderTreeDump())
            frame.render(painter)
            painter.end()

            if overwrite or not os.path.exists(pathPng):
                print('Save {}...'.format(pathPng))
                img.save(pathPng, quality=100)
            del painter, frame, img, page
            s  =""
        elif mode == 'INKSCAPE':
            if fileNeedsUpdate(pathSvg, pathPng):
                if sys.platform == 'darwin':
                    cmd = ['inkscape']
                else:
                    dirInkscape = r'C:\Program Files\Inkscape'
                    assert os.path.isdir(dirInkscape)
                    cmd = [jp(dirInkscape,'inkscape')]
                cmd.append('--file={}'.format(pathSvg))
                cmd.append('--export-png={}'.format(pathPng))
                from subprocess import PIPE
                p = subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
                output, err = p.communicate()
                rc = p.returncode
                print('Saved {}'.format(pathPng))
                if err != '':
                    buggySvg.append((pathSvg, err))

    if len(buggySvg) > 0:
        six._print('SVG Errors')
        for t in buggySvg:
            pathSvg, error = t
            six._print(pathSvg, error, file=sys.stderr)
    s = ""


def png2qrc(icondir, pathQrc, pngprefix='vrtbuilder'):
    pathQrc = os.path.abspath(pathQrc)
    dirQrc = os.path.dirname(pathQrc)
    app = QApplication([])
    assert os.path.exists(pathQrc)
    doc = QDomDocument('RCC')
    doc.setContent(QFile(pathQrc))
    if str(doc.toString()) == '':
        doc.appendChild(doc.createElement('RCC'))
    root = doc.documentElement()
    pngFiles = set()
    fileAttributes = {}
    #add files already included in QRC

    fileNodes = doc.elementsByTagName('file')
    for i in range(fileNodes.count()):
        fileNode = fileNodes.item(i).toElement()

        file = str(fileNode.childNodes().item(0).nodeValue())
        if file.lower().endswith('.png'):
            pngFiles.add(file)
            if fileNode.hasAttributes():
                attributes = {}
                for i in range(fileNode.attributes().count()):
                    attr = fileNode.attributes().item(i).toAttr()
                    attributes[str(attr.name())] = str(attr.value())
                fileAttributes[file] = attributes

    #add new pngs in icondir
    for f in  file_search(icondir, '*.png'):
        file = os.path.relpath(f, dirQrc).replace('\\','/')
        pngFiles.add(file)

    pngFiles = sorted(list(pngFiles))

    def elementsByTagAndProperties(elementName, attributeProperties, rootNode=None):
        assert isinstance(elementName, str)
        assert isinstance(attributeProperties, dict)
        if rootNode is None:
            rootNode = doc
        resourceNodes = rootNode.elementsByTagName(elementName)
        nodeList = []
        for i in range(resourceNodes.count()):
            resourceNode = resourceNodes.item(i).toElement()
            for aName, aValue in attributeProperties.items():
                if resourceNode.hasAttribute(aName):
                    if aValue != None:
                        assert isinstance(aValue, str)
                        if str(resourceNode.attribute(aName)) == aValue:
                            nodeList.append(resourceNode)
                    else:
                        nodeList.append(resourceNode)
        return nodeList


    resourceNodes = elementsByTagAndProperties('qresource', {'prefix':pngprefix})

    if len(resourceNodes) == 0:
        resourceNode = doc.createElement('qresource')
        root.appendChild(resourceNode)
        resourceNode.setAttribute('prefix', pngprefix)
    elif len(resourceNodes) == 1:
        resourceNode = resourceNodes[0]
    else:
        raise NotImplementedError('Multiple resource nodes')

    #remove childs, as we have all stored in list pngFiles
    childs = resourceNode.childNodes()
    while not childs.isEmpty():
        node = childs.item(0)
        node.parentNode().removeChild(node)

    #insert new childs
    for pngFile in pngFiles:

        node = doc.createElement('file')
        attributes = fileAttributes.get(pngFile)
        if attributes:
            for k, v in attributes.items():
                node.setAttribute(k,v)
            s = 2
        node.appendChild(doc.createTextNode(pngFile))
        resourceNode.appendChild(node)
        print(pngFile)

    f = open(pathQrc, "w")
    f.write(doc.toString())
    f.close()


def updateMetadataTxt():
    #see http://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/plugins.html#plugin-metadata
    #for required & optional meta tags
    pathDst = jp(DIR_ROOT, 'metadata.txt')
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
    md['qgisMinimumVersion'] = "2.18"
    #md['qgisMaximumVersion'] =
    md['description'] = vrtbuilder.DESCRIPTION.strip()
    md['about'] = vrtbuilder.ABOUT.replace('\n',' ').strip()
    md['version'] = vrtbuilder.VERSION.strip()
    md['author'] = "Benjamin Jakimow, Geomatics Lab, Humboldt-Universität zu Berlin"
    md['email'] = "benjamin.jakimow@geo.hu-berlin.de"
    #md['changelog'] =
    md['experimental'] = "True"
    md['deprecated'] = "False"
    md['tags'] = "remote sensing, raster"
    md['homepage'] = vrtbuilder.WEBSITE
    md['repository'] = vrtbuilder.WEBSITE
    md['tracker'] = vrtbuilder.WEBSITE+'/issues'
    md['icon'] = 'vrtbuilder/ui/mActionNewVirtualLayer.png'
    md['category'] = 'Raster'

    lines = ['[general]']
    for k, line in md.items():
        lines.append('{}={}\n'.format(k, line))
    open(pathDst, 'w').writelines('\n'.join(lines))
    s = ""


def updateHelpHTML():
    import markdown, urllib
    import vrtbuilder
    from vrtbuilder import DIR_ROOT
    """
    Keyword arguments:

    * input: a file name or readable object.
    * output: a file name or writable object.
    * encoding: Encoding of input and output.
    * Any arguments accepted by the Markdown class.
    """

    markdownExtension = [
        'markdown.extensions.toc',
        'markdown.extensions.tables',
        'markdown.extensions.extra'
    ]

    def readUrlTxt(url):
        req = urllib.urlopen(url)
        enc = req.headers['content-type'].split('charset=')[-1]
        txt = req.read()
        req.close()
        if enc == 'text/plain':
            return unicode(txt)
        return unicode(txt, enc)
    pathSrc = os.path.join(DIR_ROOT, *['vrtbuilder', 'help.md'])
    pathDst = jp(os.path.dirname(vrtbuilder.__file__), 'help.html')
    markdown.markdownFromFile(input=pathSrc,
                              extensions=markdownExtension,
                              output=pathDst, output_format='html5')


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
        if True:
            import subprocess
            import make


            os.chdir(DIR_ROOT)
            subprocess.call(['pb_tool', 'compile'])
            make.compile_rc_files(DIR_ROOT)

        else:
            cfgParser = pb_tool.get_config(config=pathCfg)
            pb_tool.compile_files(cfgParser)

        #3. Deploy = write the data to the new enmapboxplugin folder
        pb_tool.deploy_files(pathCfg, confirm=False)

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
        pathQGIS = os.path.join(expanduser("~"), *['.qgis2','python','plugins'])

        assert os.path.isdir(pathQGIS)
        pathDst = os.path.join(pathQGIS, os.path.basename(dirPlugin))
        rm(pathDst)
        shutil.copytree(dirPlugin, pathDst)
        s  =""


    print('Finished')



if __name__ == '__main__':
    icondir = jp(DIR_UI)
    pathQrc = jp(DIR_UI,'resources.qrc')


    if False:
        updateMetadataTxt()
        updateHelpHTML()
        #exit()
    if False:
        #convert SVG to PNG and link them into the resource file
        svg2png(icondir, overwrite=False)

    if False:
        #add png icons to qrc file
        png2qrc(icondir, pathQrc)

    if True:
        compile_rc_files(DIR_UI)

    if False:
        deploy()
    print('Done')

