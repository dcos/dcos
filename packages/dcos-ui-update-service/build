#!/bin/bash

set -e  # Fail the script if anything fails
set -x  # Verbose output
set -u  # Undefined variables

mkdir -p "$PKG_PATH"/bin
mv "/pkg/src/dcos-ui-update-service/dcos-ui-update-service-"* "$PKG_PATH"/bin/dcos-ui-update-service
chmod +x "$PKG_PATH"/bin/dcos-ui-update-service

# Create the service file
service="$PKG_PATH/dcos.target.wants_master/dcos-ui-update-service.service"
mkdir -p "$(dirname "$service")"
cp /pkg/extra/dcos-ui-update-service.service  "$service"

# Create the socket file
socket="$PKG_PATH/dcos.target.wants_master/dcos-ui-update-service.socket"
mkdir -p "$(dirname "$socket")"
cp /pkg/extra/dcos-ui-update-service.socket "$socket"

# Create service pre-start file
cp /pkg/extra/dcos-ui-update-service-pre-start.sh "$PKG_PATH"/dcos-ui-update-service-pre-start.sh
chmod +x "$PKG_PATH"/dcos-ui-update-service-pre-start.sh
