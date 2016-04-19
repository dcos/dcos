#!/bin/bash
set -o errexit -o nounset -o pipefail -x

# Make files in bin/lib will likely touch bin, lib of output. Test that.
mkdir -p "$PKG_PATH/bin" "$PKG_PATH/lib"
touch "$PKG_PATH/bin/$PKG_NAME"
touch "$PKG_PATH/lib/$PKG_NAME.so"
echo "$PKG_VERSION" > "$PKG_PATH/version"
touch "$PKG_PATH/$PKG_NAME"
sudo chmod -R o+w $PKG_PATH
