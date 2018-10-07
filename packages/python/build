#!/bin/bash
# Build
set -ex

mkdir -p build
pushd build

export CFLAGS=-I/opt/mesosphere/include
export LDFLAGS="-L/opt/mesosphere/lib -Wl,-rpath=/opt/mesosphere/lib"
export CPPFLAGS=-I/opt/mesosphere/include

/pkg/src/python/configure --enable-shared --prefix="$PKG_PATH" --enable-ipv6 --with-threads --with-computed-gotos
make -j$NUM_CORES
make install

# Install the build-specific gdb helper artifact
cp python-gdb.py "$PKG_PATH/share/"

# Remove some big things we don't use at all
rm -rf "$PKG_PATH/lib/python3.6/test"

# TODO(cmaloney): This sort of stripping static libraries should be a generic
# mkpanda option to apply to any package.
find "$PKG_PATH/lib/" ! -type d -name "*.a" -exec rm -f -- '{}' +

# Take control of setuptools and pip version.
# Note(JP): For making pip upgrade itself reliably, it's best
# to run pip as a module (python -m pip).
export LD_LIBRARY_PATH=$PKG_PATH/lib
export LIB_INSTALL_DIR="$PKG_PATH/lib/python3.6/site-packages"
$PKG_PATH/bin/python3 -m pip install --upgrade --no-deps --install-option="--prefix=$PKG_PATH" --root=/ /pkg/src/setuptools/*.whl

$PKG_PATH/bin/python3 -m pip install --upgrade --no-deps --install-option="--prefix=$PKG_PATH" --root=/ /pkg/src/pip
echo "pip version: $($PKG_PATH/bin/pip3 --version)"


# Setup helper symlinks, force overwrite if link name exists.
ln -fs "$PKG_PATH/bin/python3" "$PKG_PATH/bin/python"
ln -fs "$PKG_PATH/bin/easy_install-3.6" "$PKG_PATH/bin/easy_install-3"
ln -fs "$PKG_PATH/bin/easy_install-3" "$PKG_PATH/bin/easy_install"
ln -fs "$PKG_PATH/bin/pip3" "$PKG_PATH/bin/pip"
ln -fs "$PKG_PATH/bin/python3-config" "$PKG_PATH/bin/python-config"
ln -fs "$PKG_PATH/bin/idle3" "$PKG_PATH/bin/idle"
ln -fs "$PKG_PATH/bin/pydoc3"  "$PKG_PATH/bin/pydoc"

# Install Cython as part of the pgkpanda `python` package so that
# pkgpanda packages that declare the `python` package as a dependency
# will find Cython to be installed. During some Python package
# installations this will result in special build variants with
# performance improvements.
$PKG_PATH/bin/python3 -m pip install --no-deps --install-option="--prefix=$PKG_PATH" --root=/ /pkg/src/cython

