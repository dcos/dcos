#!/bin/bash

set -o errexit
set -o xtrace
set -o nounset

# Install the package that provides envsubst.
apt-get update && apt-get install gettext-base
which envsubst

# Install dep to enable the deps target in Telegraf's Makefile.
dep_version=0.5.0
curl -L -s https://github.com/golang/dep/releases/download/v$dep_version/dep-linux-amd64 -o $GOPATH/bin/dep
chmod a+x $GOPATH/bin/dep

project="github.com/influxdata/telegraf"
project_src_path="$GOPATH/src/$project"

# Add the project to $GOPATH.
mkdir -p $(dirname $project_src_path)
ln -s /pkg/src/$PKG_NAME $project_src_path

# Build telegraf and add it to the package.
mkdir -p $PKG_PATH/bin/
(cd $project_src_path && make deps && make telegraf)
mv $project_src_path/telegraf $PKG_PATH/bin/
# Add the telegraf startup script to the package.
cp /pkg/extra/start_telegraf.sh $PKG_PATH/bin/

# Create dcos-telegraf unit files.
# Telegraf uses one service account on masters and another on agents and public agents.
unit_template="/pkg/extra/dcos-telegraf.service"
master_unit="$PKG_PATH/dcos.target.wants_master/dcos-telegraf.service"
agent_unit="$PKG_PATH/dcos.target.wants_slave/dcos-telegraf.service"
agent_public_unit="$PKG_PATH/dcos.target.wants_slave_public/dcos-telegraf.service"

# Add the master unit file to the package.
mkdir -p $(dirname $master_unit)
SERVICE="dcos-telegraf-master" envsubst '${SERVICE} ${PKG_PATH}' < $unit_template > $master_unit

# Add the agent unit files to the package.
for unit in $agent_unit $agent_public_unit; do
  mkdir -p $(dirname $unit)
  SERVICE="dcos-telegraf-agent" envsubst '${SERVICE} ${PKG_PATH}' < $unit_template > $unit
done

# Add the socket unit to the package for all roles.
socket_unit="$PKG_PATH/dcos.target.wants/dcos-telegraf.socket"
mkdir -p $(dirname $socket_unit)
cp /pkg/extra/dcos-telegraf.socket $socket_unit

# Add tools to the package.
cp -r /pkg/extra/tools/ "${PKG_PATH}"
