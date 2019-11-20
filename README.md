# README #

The Virtual Raster Builder is a [QGIS](http://www.qgis.org) plugin to create
[GDAL](http://gdal.org) [Virtual Raster (VRT)](http://www.gdal.org/gdal_vrttut.html).
It provides an interactive user interface that uses drag and drop to
describe the structure of a new virtual or binary raster image.

In particular it can be used to create:

- band stacks
- band subsets
- spatial mosaics
- spatial subsets

all at the same time (which yet is not possible using [gdalbuildvrt](http://www.gdal.org/gdalbuildvrt.html) or the
QGIS core "Build Virtual Raster" Tool that is based on.)


![workflow](workflow.png)


Other features:

- input images can be of different projection systems, which will be translated using warped VRTs files
- output as binary raster images (supported formats: GeoTIFF, ENVI (BSQ,BIL,BIP))
- spatial extents can be selected inside the QGIS MapCanvas
- a preview map canvas shows the spatial extents of the source images
- selection of input image bands within tree view or preview map canvas



A short help how to use the Virtual Raster Bulder is given here [here](doc/source/index.rst).
# Licence and Use #

The Virtual Raster Builder is licenced under the [GPL-3 Licence](LICENSE.txt).
