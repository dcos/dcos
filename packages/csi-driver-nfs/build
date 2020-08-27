#!/bin/bash
set -o errexit -o nounset -o pipefail

srcdir=$GOPATH/src/github.com/kubernetes-csi/csi-driver-nfs
mkdir -p $(dirname $srcdir)
ln -s /pkg/src/csi-driver-nfs $srcdir
cd $srcdir

make

mkdir -p $PKG_PATH/bin
mv $srcdir/bin/nfsplugin $PKG_PATH/bin
