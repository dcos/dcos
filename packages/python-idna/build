#!/bin/bash
source /opt/mesosphere/environment.export
export LIB_INSTALL_DIR="$PKG_PATH/lib/python3.6/site-packages"
mkdir -p "$LIB_INSTALL_DIR"

pip install --no-deps --no-index --prefix=$PKG_PATH /pkg/src/$PKG_NAME/*.whl
