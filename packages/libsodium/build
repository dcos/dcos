#!/bin/bash

mkdir -p build
pushd build

cd /pkg/src/libsodium
./configure --prefix="$PKG_PATH"
make -j$NUM_CORES
make install
