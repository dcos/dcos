#!/bin/bash
source /opt/mesosphere/environment.export
export LIB_INSTALL_DIR="$PKG_PATH/lib/python3.6/site-packages"
mkdir -p "$LIB_INSTALL_DIR"

export PKG_CONFIG_PATH=/opt/mesosphere/lib/pkgconfig

for package in cffi cryptography; do
  pip3 install --no-deps --install-option="--prefix=$PKG_PATH" --root=/ /pkg/src/$package/
done

