"""
Initial setup of the VRT Raster Builder repository.
"""

# specify the local path to the cloned QGIS repository
import os
import sys
import site
import pathlib


def setup_repository():

    DIR_REPO = pathlib.Path(__file__).parents[1].resolve()
    site.addsitedir(DIR_REPO)

    from scripts.compile_resourcefiles import compileVRTBuilderResources
    from scripts.install_testdata import install_qgisresources
    print('Compile VRT Raster Builder resources')
    compileVRTBuilderResources()

    print('Install QGIS resource files')
    install_qgisresources()

    print('VRT Raster Builder repository setup finished')

if __name__ == "__main__":
    print('setup repository')
    setup_repository()
