#!/bin/bash
mkdir -p /pkg/src/github.com/dcos
# Create the GOPATH for the go tool to work properly
mv /pkg/src/dcos-check-runner /pkg/src/github.com/dcos/
cd /pkg/src/github.com/dcos/dcos-check-runner/
make install
# Copy the build from the bin to the correct place
cp -r /pkg/bin/ "$PKG_PATH"

# Permissions bootstraping is defined once in the api service file since that
# is started once and left running rather than needing to run every minute
# Destination for the service files
master_service="${PKG_PATH}/dcos.target.wants_master/dcos-checks-api.service"
agent_service="${PKG_PATH}/dcos.target.wants_slave/dcos-checks-api.service"
agent_public_service="${PKG_PATH}/dcos.target.wants_slave_public/dcos-checks-api.service"

master_socket="${PKG_PATH}/dcos.target.wants_master/dcos-checks-api.socket"
agent_socket="${PKG_PATH}/dcos.target.wants_slave/dcos-checks-api.socket"
agent_public_socket="${PKG_PATH}/dcos.target.wants_slave_public/dcos-checks-api.socket"

mkdir -p "$(dirname "$master_service")"
mkdir -p "$(dirname "$agent_service")"
mkdir -p "$(dirname "$agent_public_service")"

cp /pkg/extra/dcos-checks-api-master.service "$master_service"
cp /pkg/extra/dcos-checks-api-agent.service "$agent_service"
cp /pkg/extra/dcos-checks-api-agent.service "$agent_public_service"

cp /pkg/extra/dcos-checks-api.socket "$master_socket"
cp /pkg/extra/dcos-checks-api.socket "$agent_socket"
cp /pkg/extra/dcos-checks-api.socket "$agent_public_socket"

# Create the poststart check service and timer
service="$PKG_PATH/dcos.target.wants/dcos-checks-poststart.service"
mkdir -p "$(dirname "$service")"
cp /pkg/extra/dcos-checks-poststart.service "$service"
timer="$PKG_PATH/dcos.target.wants/dcos-checks-poststart.timer"
mkdir -p "$(dirname "$timer")"
cp /pkg/extra/dcos-checks-poststart.timer "$timer"
