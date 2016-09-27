#!/bin/bash
# Build
mkdir -p build
pushd build

cd /pkg/src/logrotate
./autogen.sh
./configure --prefix="$PKG_PATH" --sbindir="$PKG_PATH/bin"
make
make install


systemd_master="$PKG_PATH"/dcos.target.wants_master/dcos-logrotate-master.service
mkdir -p "$(dirname "$systemd_master")"
envsubst '$PKG_PATH' < /pkg/extra/dcos-logrotate-master.service > "$systemd_master"

systemd_agent="$PKG_PATH"/dcos.target.wants_slave/dcos-logrotate-agent.service
mkdir -p "$(dirname "$systemd_agent")"
envsubst '$PKG_PATH' < /pkg/extra/dcos-logrotate-agent.service > "$systemd_agent"

systemd_agent_public="$PKG_PATH"/dcos.target.wants_slave_public/dcos-logrotate-agent.service
mkdir -p "$(dirname "$systemd_agent_public")"
envsubst '$PKG_PATH' < /pkg/extra/dcos-logrotate-agent.service > "$systemd_agent_public"


logrotate_timer="/pkg/extra/dcos-logrotate.timer"
cp "$logrotate_timer" "$PKG_PATH/dcos.target.wants_master/dcos-logrotate-master.timer"
cp "$logrotate_timer" "$PKG_PATH/dcos.target.wants_slave/dcos-logrotate-agent.timer"
cp "$logrotate_timer" "$PKG_PATH/dcos.target.wants_slave_public/dcos-logrotate-agent.timer"


postrotate_script="$PKG_PATH/bin/delete-oldest-unmanaged-files.py"
cp /pkg/extra/delete-oldest-unmanaged-files.py "$postrotate_script"
chmod +x "$postrotate_script"