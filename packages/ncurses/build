#!/bin/bash

mkdir -p build
pushd build

cd /pkg/src/ncurses
./configure --prefix="$PKG_PATH" --with-termlib --with-ticlib
make -j$NUM_CORES
make install
