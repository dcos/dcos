#!/bin/bash
source /opt/mesosphere/environment.export
export LIB_INSTALL_DIR="$PKG_PATH/lib/python3.6/site-packages"
mkdir -p "$LIB_INSTALL_DIR"

export PKG_CONFIG_PATH=/opt/mesosphere/lib/pkgconfig

# Work around https://github.com/sybrenstuvel/python-rsa/pull/122
echo "" > /pkg/src/rsa/README.md

for package in ecdsa rsa python-jose; do
    # ecdsa and rsa are slow Python implementations.
    # We also install cryptography for off-loading
    # work to OpenSSL. However, python-jose will not
    # work (as of ImportErrors) w/o rsa and ecdsa
    # installed.
    # Note(JP): this might be a good reason for using pyjwt in
    # Bouncer for JWKS parsing.
    pip3 install --no-deps --install-option="--prefix=$PKG_PATH" --root=/ /pkg/src/$package/
done

