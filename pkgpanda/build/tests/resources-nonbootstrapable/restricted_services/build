#!/bin/bash
set -o errexit -o nounset -o pipefail -x

# Make files in bin/lib will likely touch bin, lib of output. Test that.
mkdir -p "$PKG_PATH/bin" "$PKG_PATH/lib" "$PKG_PATH/dcos.target.wants"
touch "$PKG_PATH/bin/mesos-master"
touch "$PKG_PATH/lib/libmesos.so"
touch "$PKG_PATH/dcos.target.wants/dcos-foo.service"
touch "$PKG_PATH/dcos.target.wants/dcos.target"
echo "$PKG_VERSION" > "$PKG_PATH/version"
touch "$PKG_PATH/$PKG_NAME"
sudo chmod -R o+w $PKG_PATH
