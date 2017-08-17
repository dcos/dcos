#!/bin/bash
set -o nounset -o pipefail

pushd /pkg/src/cni/
./build.sh
popd

cp /pkg/src/cni/bin/* $PKG_PATH
