#!/bin/bash

mkdir -p build
pushd build

export CFLAGS=-I/opt/mesosphere/include
export LDFLAGS="-L/opt/mesosphere/lib -Wl,-rpath=/opt/mesosphere/lib"
export CPPFLAGS=-I/opt/mesosphere/include

cd /pkg/src/libevent
./autogen.sh
./configure --prefix="$PKG_PATH"
make
make install
