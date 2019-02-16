#!/bin/bash

set -exu

source /opt/mesosphere/environment.export
export LIB_INSTALL_DIR="$PKG_PATH/lib/python3.6/site-packages"
mkdir -p "$LIB_INSTALL_DIR"

# All dependencies shared between upstream and downstream Bouncer
# must be set up via the `bouncer-deps` pkgpanda package so that
# it can be included in the `ee` variant of the `bouncer` pkgpanda
# package as well.

echo "pip version: $(pip --version)"

# Resolve 'Package libffi was not found in the pkg-config search path'.
export PKG_CONFIG_PATH=/opt/mesosphere/lib/pkgconfig


# Install bouncer by copying the entire directory tree.
# Note(JP): we could cherry-pick what is required.
cp -r "/pkg/src/bouncer" "$PKG_PATH/bouncer"

# Deploy systemd service file.
SERVICE_FILE_NAME="dcos-bouncer.service"
SERVICE_FILE_PATH="$PKG_PATH/dcos.target.wants_master/${SERVICE_FILE_NAME}"
mkdir -p "$(dirname "$SERVICE_FILE_PATH")"
envsubst '$PKG_PATH' < "/pkg/extra/${SERVICE_FILE_NAME}" > "${SERVICE_FILE_PATH}"

# Copy the IAM users migration script to the package bin directory.
mkdir -p $PKG_PATH/bin
install -m 755 /pkg/extra/iam-migrate-users-from-zk.py $PKG_PATH/bin/iam-migrate-users-from-zk.py

# Copy the IAM user creation script
install -m 755 /pkg/extra/dcos_add_user.py $PKG_PATH/bin/dcos_add_user.py

cp /pkg/extra/dcos-bouncer-migrate-users.service "$PKG_PATH/dcos.target.wants_master/dcos-bouncer-migrate-users.service"
