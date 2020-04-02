#!/bin/bash

# Marathon and Metronome use the same jars, and pkgpanda doens't allow two packages
# to have files at the same path, so essentially make marathon package-private.
# Nothing will end up in /opt/mesosphere/{bin, lib}
# This is not ideal but its one of the few solutions.
# the lib directory is _supposed_ to be in the parent of $(realpath bin/marathon)
# and its unclear how to change that without creating a very custom zipfile
# that is different.

source /opt/mesosphere/environment.export

mkdir -p "$PKG_PATH/marathon/bin"
mkdir -p "$PKG_PATH/marathon/lib"

cp -rp /pkg/src/marathon/bin/marathon "$PKG_PATH/marathon/bin/marathon"
chmod +x "$PKG_PATH/marathon/bin/marathon"
cp -rpn /pkg/src/marathon/lib/*.jar "$PKG_PATH/marathon/lib"

marathon_wrapper="$PKG_PATH/bin/marathon.sh"
mkdir -p "$(dirname "$marathon_wrapper")"
envsubst '$PKG_PATH' < /pkg/extra/marathon.sh > "$marathon_wrapper"
chmod +x "$marathon_wrapper"

marathon_service="$PKG_PATH/dcos.target.wants_master/dcos-marathon.service"
mkdir -p $(dirname "$marathon_service")

cat <<EOF > "$marathon_service"
[Unit]
Description=Marathon: container orchestration engine
[Service]
User=dcos_marathon
Restart=always
StartLimitInterval=0
RestartSec=15
LimitNOFILE=16384
PermissionsStartOnly=True
# The env files in /opt are overwritten on upgrade
EnvironmentFile=/opt/mesosphere/environment
EnvironmentFile=/opt/mesosphere/etc/marathon
EnvironmentFile=-/opt/mesosphere/etc/marathon-extras
EnvironmentFile=-/run/dcos/etc/marathon/tls.env
EnvironmentFile=-/run/dcos/etc/marathon/zk.env
# The env file in /var/lib/dcos is for post-install configuration and persists with upgrades.
EnvironmentFile=-/var/lib/dcos/marathon/environment
Environment=JAVA_HOME=${JAVA_HOME}
ExecStartPre=/bin/ping -c1 leader.mesos
ExecStartPre=/opt/mesosphere/bin/bootstrap dcos-marathon
ExecStart=/opt/mesosphere/bin/marathon.sh
EOF
