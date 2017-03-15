#!/bin/bash

pushd "/pkg/src/libffi"
./configure "--prefix=$PKG_PATH"
make
make install

find "$PKG_PATH/lib/" ! -type d -name "*.a"  -delete
rm -rf "$PKG_PATH/share/"
