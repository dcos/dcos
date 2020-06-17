#!/bin/bash

set -o errexit
set -o xtrace
set -o nounset

# Build and install Fluent Bit.
# https://docs.fluentbit.io/manual/installation/build_install
pushd "/pkg/src/$PKG_NAME/build"
# FLB_TLS:         enable TLS support
# FLB_METRICS:     fluent bit's metrics
# FLB_HTTP_SERVER: API for metrics collection
# FLB_SQLDB:       use an SQLite DB to track log cursors
# FLB_PROXY_GO:    enable proxy plugins support
# DFLB_JEMALLOC:   use jemalloc to avoid fragmentation
cmake -DCMAKE_INSTALL_PREFIX="$PKG_PATH" -DFLB_TLS="On" -DFLB_METRICS="On" -DFLB_HTTP_SERVER="On" -DFLB_SQLDB="On" -DFLB_PROXY_GO="On" -DFLB_JEMALLOC=On ../
make
make install
popd
# Remove Fluent Bit's default config.
rm -rf "$PKG_PATH/etc"

# Add systemd unit file.
unit_file="$PKG_PATH/dcos.target.wants/dcos-fluent-bit.service"
mkdir -p "$(dirname "$unit_file")"
cp "/pkg/extra/dcos-fluent-bit.service" "$unit_file"
