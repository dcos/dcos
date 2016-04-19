#!/bin/bash
# Build
mkdir -p build
pushd build

cd /pkg/src/strace
./configure --prefix="$PKG_PATH"
make
make install
