..  Virtual Raster Builder documentation master file, created by
    sphinx-quickstart on Fri Jan 19 05:59:30 2018.
    You can adapt this file completely to your liking, but it should at least
    contain the root `toctree` directive.


.. Substitutions (for p in os.listdir(r'D:\Repositories\QGIS_Plugins\virtual-raster-builder\doc\source\img'): print('.. |{}| image:: img/{}'.format(p,p)))

.. |mActionAddRasterLayer.png| image:: img/mActionAddRasterLayer.png
.. |mActionAddVirtualRaster.png| image:: img/mActionAddVirtualRaster.png
.. |mActionCollapseTree.png| image:: img/mActionCollapseTree.png
.. |mActionExpandTree.png| image:: img/mActionExpandTree.png
.. |mActionImportFromRegistry.png| image:: img/mActionImportFromRegistry.png
.. |mActionImportRaster.png| image:: img/mActionImportRaster.png
.. |mActionImportVirtualRaster.png| image:: img/mActionImportVirtualRaster.png
.. |mActionNewVirtualLayer.png| image:: img/mActionNewVirtualLayer.png
.. |mActionPan.png| image:: img/mActionPan.png
.. |mActionRemoveRasterLayer.png| image:: img/mActionRemoveRasterLayer.png
.. |mActionRemoveVirtualRaster.png| image:: img/mActionRemoveVirtualRaster.png
.. |mActionSelect.png| image:: img/mActionSelect.png
.. |mActionZoomFullExtent.png| image:: img/mActionZoomFullExtent.png
.. |mActionZoomIn.png| image:: img/mActionZoomIn.png
.. |mActionZoomOut.png| image:: img/mActionZoomOut.png
.. |mIconRaster.png| image:: img/mIconRaster.png
.. |mIconVirtualRaster.png| image:: img/mIconVirtualRaster.png
.. |mOptionMosaikFiles.png| image:: img/mOptionMosaikFiles.png
.. |mOptionStackFiles.png| image:: img/mOptionStackFiles.png


Virtual Raster Builder Documentation
=======================================

The Virtual Raster Builder helps to define GDAL Virtual Raster (VRT) files by drag and drop.
It helps to create a new raster image by stacking, mosaiking, spatial- oder band-subsetting.




Workflow
--------

.. image:: img/workflow.png

1. Add potential source files to the list of source files:

    ===============================  ================================================
    Button                           Action
    ===============================  ================================================
    |mActionAddRasterLayer.png|      Add source raster
    |mActionRemoveRasterLayer.png|   Remove source raster
    |mActionImportFromRegistry.png|  Load source raster files that are known to QGIS
    |mActionExpandTree.png|          expand source file tree node(s)
    |mActionCollapseTree.png|        collapse source file tree node(s)
    ===============================  ================================================

2. Specify the VRT structure by drag and drop of source bands

    ================================  ===========================================
    Button                            Action
    ================================  ===========================================
    |mActionAddVirtualRaster.png|     Add virtual band
    |mActionRemoveVirtualRaster.png|  Remove virtual band
    |mActionImportVirtualRaster.png|  Import virtual bands from existing VRT file
    |mActionExpandTree.png|           Expand VRT tree node(s)
    |mActionCollapseTree.png|         Collapse VRT tree node(s)
    ================================  ===========================================

    Virtual band names can be changed by mouse double-click.

3. Specify other VRT settings:

      * set spatial resolution
      * set the resampling method
      * set spatial extent
      * set output format

4. Save the new file as VRT. In case of output formats other than VRT, e.g. GeoTIFF,
the VRT is created in a temporary location first and the binary file
afterwards using `gdal.Translate <http://gdal.org/python/osgeo.gdal-module.html#TranslateOptions>`_.

Licence and Use
---------------

The Virtual Raster Builder is licenced under the `GPL-3 Licence <https://www.gnu.org/licenses/gpl-3.0.html>`_.


