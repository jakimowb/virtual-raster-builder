0.9 2021-02-10
   * fixed loading from VRt files (#23)
   * main window got a toolbar and dock widgets
   * improved tree models, e.g. to list raster sources
   * can read multi-layer sources
   * spatial extents can be selected from different map canvases, e.g QGIS or EnMAP-box

0.8 2020-08-09:
   * fixed updating of VRT output extent
   * added menu bar
   * modified context menu of VRT tree, e.g. to rename VRT Bands

0.7 2019-11-20:
   * documentation now online on https://virtual-raster-builder.readthedocs.io/en/latest/
   * widgets to specify the output extent will be disable if auto-extent is enabled
   * output raster size in px can be now set to values larger 99px (#18)
   * spatial extent can be selected from QGIS map canvas (#17)
   * selected tree-view rows now have a yellow background (#15)
   * removed error when clicking on empty VRT band (#14)

0.6 2019-06-04:
    * preview window shows extent of VRT raster sources
    * added options to copy raster grid properties (resolution, extent) from other rasters (#12)
    * added option to align the VRR rastergrid to that of another raster image (#12)
    * included QPS library for faster updates

0.5 2018-06-15:
    * supports in-memory files based on GDAL "/vsimem/"
    * does not require temporal local VRT files any more
    * fixed bug #9 "Save VRT error"

0.4 Mai 2018:
    * fixed bug #6 drag 'n drop from QGIS 3 layer list
    * fixed bug #7 import of raster layers known to QGIS MapLayerRegistry
    * enhancement #7 VRTs can now be written with empty virtual raster bands (but have to define at least one virtual band)
    * fixed bug #10 removal of selected data sources

0.3 2018-03-02:
    * Code-base converted to PyQt5 and QGIS 3
    * Small fixes of smaller UI response issues
    * Sphinx - based documentation, documentation is also shown in the "help" tab