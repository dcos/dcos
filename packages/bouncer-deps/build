#!/bin/bash

# This is for installing bouncer dependencies that are required
# in both, upstream (variant 'default') and downstream (variant
# 'ee') bouncer.

set -exu

source /opt/mesosphere/environment.export
export LIB_INSTALL_DIR="$PKG_PATH/lib/python3.6/site-packages"
mkdir -p "$LIB_INSTALL_DIR"

echo "pip version: $(pip --version)"
echo "Install packages from wheel files."
pip install --no-deps --no-index --target="$LIB_INSTALL_DIR" /pkg/src/jsonschema/*.whl

# Resolve 'Package libffi was not found in the pkg-config search path'.
export PKG_CONFIG_PATH=/opt/mesosphere/lib/pkgconfig

# Install from local source directories (git checkout or extracted tarballs).
# Order matters. Some of these packages require Cython or build C extensions
# for speed-up if Cython is availble.
echo "Install packages from local source directories."
for package in \
    falcon \
    python-mimeparse \
    sqlalchemy \
    sqlalchemy-utils \
    mako \
    python-editor \
    alembic \
    cockroachdb-python \
    psycopg2 \
    pyasn1
do
  pip install -v --no-deps --install-option="--prefix=$PKG_PATH" --root=/ /pkg/src/$package
done
