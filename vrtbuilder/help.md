## Virtual Raster Builder

![VRT Builder Logo](ui/mActionNewVirtualLayer.png)

[TOC]

## Description

The Virtual Raster Builder is a tool to create a [GDAL Virtual Raster](http://www.gdal.org/gdal_vrttut.html)
(VRT) by drag and drop. It can be used to stack and mosaic rasterbands or to create spatial- or band-subsets.


## Workflow

To build a new virtual raster (VRT) follow these steps:

1. Add potential source files to the list of source files:


    | Button | Action |
    |----------|----------|
    | ![add source raster](ui/mActionAddRasterLayer.png){: width=32 height=32}| add source raster |
    | ![remove source raster](ui/mActionRemoveRasterLayer.png){: width=32 height=32}      | remove source raster |
    | ![import from QGIS](ui/mActionImportFromRegistry.png){: width=32 height=32} | load raster known to QGIS |
    | ![expand tree node](ui/mActionExpandTree.png){: width=32 height=32}| expand source file tree node(s) |
    | ![collapse tree node](ui/mActionCollapseTree.png){: width=32 height=32}| collapse source file tree node(s) |


2. Specify the VRT structure by drag and drop of source bands

    | Button | Action |
    |----------|----------|
    | ![add virtual band](ui/mActionAddVirtualRaster.png){: width=32 height=32} | add virtual band|
    | ![remove virtual band](ui/mActionRemoveVirtualRaster.png){: width=32 height=32}      | remove virtual band|
    | ![import virtual bands from existing VRT file](ui/mActionImportVirtualRaster.png){: width=32 height=32} | import virtual bands from existing VRT file |
    | ![expand tree node](ui/mActionExpandTree.png){: width=32 height=32}| expand VRT tree node(s) |
    | ![collapse tree node](ui/mActionCollapseTree.png){: width=32 height=32}| collapse VRT tree node(s) |

    Virtual band names can be changed by mouse double-click.

3. Specify other VRT settings:

      * set spatial resolution
      * set the resampling method
      * set spatial extent
      * set output format

4. Save the new file as VRT. In case of output formats other than VRT, e.g. GeoTIFF,
the VRT is created in a temporary location first and the binary file
afterwards using [gdal.Translate](http://gdal.org/python/osgeo.gdal-module.html#TranslateOptions)

## Licence and Use

The Virtual Raster Builder is licenced under the [GPL-3 Licence](https://www.gnu.org/licenses/gpl-3.0.html).

