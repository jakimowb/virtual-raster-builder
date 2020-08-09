"""
Initial setup of the VRT Raster Builder repository.
"""

# specify the local path to the cloned QGIS repository
import os
import sys

DIR_QGIS_REPO = os.environ.get('DIR_QGIS_REPO', None)


from os.path import dirname as dn
from os.path import join as jn
DIR_REPO = dn(dn(__file__))
DIR_QGISRESOURCES = jn(DIR_REPO, 'qgisresources')

# 1. compile all resource files (*.qrc) into corresponding python modules (*.py)
from vrtbuilder.externals.qps.resources import compileResourceFiles, compileQGISResourceFiles

# 2. create the qgisresource folder
if isinstance(DIR_QGIS_REPO, str):
    pathImages = os.path.join(DIR_QGIS_REPO, *['images', 'images.qrc'])
    if not os.path.isfile(pathImages):
        print('Wrong DIR_QGIS_REPO. Unable to find QGIS images.qrc in {}'.format(DIR_QGIS_REPO), file=sys.stderr)
    else:
        compileQGISResourceFiles(DIR_QGIS_REPO)
else:
    print('DIR_QGIS_REPO undefined. Some widgets might appear without icons', file=sys.stderr)


print('VRT Raster Builder repository setup finished')

exit(0)