0.6 2019-06-04:
    * preview window shows extent of VRT raster sources
    * added options to copy raster grid properties (resolution, extent) from other rasters (`#12 <https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/12>`_)
    * added option to align the VRR rastergrid to that of another raster image (`#12 <https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/12>`_)
    * included QPS library for faster updates

0.5 2018-06-15:
    * supports in-memory files based on GDAL "/vsimem/"
    * does not require temporal local VRT files any more
    * fixed bug `#9 <https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/9>`_ "Save VRT error"

0.4 Mai 2018:
    * fixed bug `#6 <https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/6>`_ drag 'n drop from QGIS 3 layer list
    * fixed bug `#7 <https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/7>`_ import of raster layers known to QGIS MapLayerRegistry
    * enhancement `#7 <https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/7>`_ VRTs can now be written with empty virtual raster bands (but have to define at least one virtual band)
    * fixed bug `#10 <https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/10>`_ removal of selected data sources


0.3 2018-03-02:
    * Code-base converted to PyQt5 and QGIS 3
    * Small fixes of smaller UI response issues
    * Sphinx - based documentation, documentation is also shown in the "help" tab