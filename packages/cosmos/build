#!/bin/bash

mkdir -p "$PKG_PATH/lib/"
mkdir -p "$PKG_PATH/usr/"

cp -rp /pkg/src/cosmos/cosmos-*-one-jar.jar "${PKG_PATH}/usr/cosmos.jar"
chmod -R o+r "${PKG_PATH}/usr"

cosmos_service="${PKG_PATH}/dcos.target.wants_master/dcos-cosmos.service"
mkdir -p $(dirname "$cosmos_service")

cat <<EOF > "$cosmos_service"
[Unit]
Description=DC/OS Package Manager (Cosmos): installs and manages DC/OS packages from DC/OS package repositories, such as the Mesosphere Universe

[Service]
Restart=always
StartLimitInterval=0
RestartSec=15
LimitNOFILE=16384
PermissionsStartOnly=True
User=dcos_cosmos
EnvironmentFile=/opt/mesosphere/environment
EnvironmentFile=/opt/mesosphere/etc/proxy.env
ExecStartPre=/bin/ping -c1 leader.mesos
ExecStartPre=/opt/mesosphere/bin/bootstrap dcos-cosmos
ExecStart=/opt/mesosphere/bin/java \\
    -Xmx2G \\
    -Djdk.http.auth.tunneling.disabledSchemes="NTLM" \\
    -classpath ${PKG_PATH}/usr/cosmos.jar \\
    com.simontuffs.onejar.Boot \\
    -admin.port=127.0.0.1:9990 \\
    -com.mesosphere.cosmos.httpInterface=127.0.0.1:7070
EOF
