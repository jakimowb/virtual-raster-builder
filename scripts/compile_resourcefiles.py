import pathlib


def compileVRTBuilderResources():
    from vrtbuilder.externals.qps.resources import compileResourceFiles

    DIR_REPO = pathlib.Path(__file__).parents[1]
    directories = [DIR_REPO / 'vrtbuilder',
                   # DIR_REPO / 'site-packages'
                   ]

    for d in directories:
        compileResourceFiles(d)

    print('Finished')


if __name__ == "__main__":
    compileVRTBuilderResources()
