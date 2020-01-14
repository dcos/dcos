#!/bin/bash

set -e  # Fail the script if anything fails
set -x  # Verbose output
set -u  # Undefined variables

export CPPFLAGS=-I/opt/mesosphere/include
export LDFLAGS="-L/opt/mesosphere/lib -Wl,-rpath=/opt/mesosphere/lib"
export LD_LIBRARY_PATH=/opt/mesosphere/lib

mkdir $PKG_PATH/lib
cp /usr/lib/x86_64-linux-gnu/libnetfilter_conntrack.so.3 $PKG_PATH/lib
cp /usr/lib/x86_64-linux-gnu/libnfnetlink.so.0 $PKG_PATH/lib

cd /pkg/src/conntrack-tools
./configure --prefix="$PKG_PATH"

make
make install

mv $PKG_PATH/sbin $PKG_PATH/bin
