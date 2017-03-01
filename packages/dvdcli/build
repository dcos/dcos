#!/bin/bash
set -o errexit -o nounset -o pipefail

srcdir=$GOPATH/src/github.com/codedellemc/dvdcli
mkdir -p $(dirname $srcdir)
ln -s /pkg/src/dvdcli $srcdir
cd $srcdir

make

mkdir -p $PKG_PATH/bin
mv $GOPATH/bin/dvdcli $PKG_PATH/bin
