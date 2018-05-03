from os.path import dirname as dn
from os.path import join as jp

d = dn(__file__)

landsat1 = jp(d, 'landsat8.2014-08-27.tif')
landsat2 = jp(d, 'landsat8.2014-09-12.tif')
landsat2_SAD = jp(d, 'landsat8.2014-09-12_SAD.tif')
rapideye = jp(d, 'rapideye.2014-06-25.tif')