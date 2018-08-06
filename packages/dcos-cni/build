#!/bin/bash
set -o nounset -o pipefail

# install glide
curl -L -O https://github.com/Masterminds/glide/releases/download/v0.13.0/glide-v0.13.0-linux-amd64.tar.gz && \
  tar xzvf glide-v0.13.0-linux-amd64.tar.gz && \
  mv linux-amd64/glide /usr/bin


# Build and install DC/OS CNI plugins.
pushd /pkg/src/dcos-cni/
make
popd

cp /pkg/src/dcos-cni/bin/* $PKG_PATH
