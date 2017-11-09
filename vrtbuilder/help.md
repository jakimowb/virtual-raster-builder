![VRT Builder Logo](ui/mActionNewVirtualLayer.png)
# Virtual Raster Builder

The Virtual Raster Builder allows to create [GDAL Virtual Raster](http://www.gdal.org/gdal_vrttut.html)
(VRT) by simple drag and drop of source bands.

To build a new virtual raster (VRT) follow these steps:


1. Add potential source files to the list of source files:


    | Button | Action |
    |----------|----------|
    | ![add source raster](ui/mActionAddRasterLayer.png)| add source raster |
    | ![remove source raster](ui/mActionRemoveRasterLayer.png)      | remove source raster |
    | ![import from QGIS](ui/mActionImportFromRegistry.png) | load raster known to QGIS |
    | ![expand tree node](ui/mActionExpandTree.png)| expand source file tree node(s) |
    | ![collapse tree node](ui/mActionCollapseTree.png)| collapse source file tree node(s) |


2. Specify the VRT structure by drag and drop of source bands

    | Button | Action |
    |----------|----------|
    | ![add virtual band](ui/mActionAddVirtualRaster.png) | add virtual band|
    | ![remove virtual band](ui/mActionRemoveVirtualRaster.png)      | remove virtual band|
    | ![import virtual bands from existing VRT file](ui/mActionImportVirtualRaster.png) | import virtual bands from existing VRT file |
    | ![expand tree node](ui/mActionExpandTree.png)| expand VRT tree node(s) |
    | ![collapse tree node](ui/mActionCollapseTree.png)| collapse VRT tree node(s) |

    Virtual band names can be changed by mouse double-click.

3. Specify other VRT settings:

      * set spatial resolution
      * set the resampling method
      * set spatial extent
      * set output format

4. Save the new file as VRT. In case you selected another output format, like GeoTiff, the VRt is created first and then translated to it's final format using [gdal.Translate](http://gdal.org/python/osgeo.gdal-module.html#TranslateOptions)

# Licence and Use #

The Virtual Raster Builder is licenced under the [GPL-3 Licence](https://www.gnu.org/licenses/gpl-3.0.html).
