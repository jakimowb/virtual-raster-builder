# -*- coding: utf-8 -*-

import os, sys, fnmatch, six, subprocess, re
from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from PyQt4.QtSvg import *
from PyQt4.QtXml import *
from PyQt4.QtXmlPatterns import *

from PyQt4.uic.Compiler.qtproxies import QtGui

import gdal

from vrtbuilder import DIR_UI, DIR_REPO
from vrtbuilder.utils import file_search
jp = os.path.join


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
        subprocess.call(['pyrcc4', '-py2', '-o', pathPy2, pathQrc])

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
    from PyQt4.QtWebKit import QWebPage

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
    #for required metatags
    pathDst = jp(DIR_REPO, 'metadata.txt')
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
    md['about'] = vrtbuilder.ABOUT.strip()
    md['version'] = vrtbuilder.VERSION.strip()
    md['author'] = "Benjamin Jakimow, Geomatics Lab, Humboldt-Universität zu Berlin"
    md['email'] = "benjamin.jakimow@geo.hu-berlin.de"
    #md['changelog'] =
    md['experimental'] = "False"
    md['deprecated'] = "False"
    md['tags'] = "remote sensing, raster, time series"
    md['homepage'] = vrtbuilder.WEBSITE
    md['repository'] = vrtbuilder.WEBSITE
    md['tracker'] = vrtbuilder.WEBSITE+'/issues'
    md['icon'] = r'timeseriesviewer/ui/icons/icon.png'
    md['category'] = 'Raster'

    lines = ['[general]']
    for k, line in md.items():
        lines.append('{}={}'.format(k, line))
    open(pathDst, 'w').writelines('\n'.join(lines))
    s = ""



def make_pb_tool_cfg():
    pathPBToolCgf = r''

    lines = open(pathPBToolCgf).readlines()

    #main_dialog:




if __name__ == '__main__':
    icondir = jp(DIR_UI)
    pathQrc = jp(DIR_UI,'resources.qrc')


    if True:
        updateMetadataTxt()

    if True:
        #convert SVG to PNG and link them into the resource file
        svg2png(icondir, overwrite=False)
    if True:
        #add png icons to qrc file
        png2qrc(icondir, pathQrc)
    if True:
        compile_rc_files(DIR_UI)
    print('Done')

