 #!/bin/bash

set -ex

cd /pkg/src/etcd

# Copy the etcd binary to the the package bin directory.
mkdir -p $PKG_PATH/bin
install -m 755 /pkg/src/etcd/etcd $PKG_PATH/bin/
install -m 755 /pkg/src/etcd/etcdctl $PKG_PATH/bin/

# Copy the registration script to the package bin directory.
install -m 755 /pkg/extra/etcd_discovery/etcd_discovery.py $PKG_PATH/bin/

# Copy the launch script to the package bin directory.
install -m 755 /pkg/extra/systemd/etcd.sh $PKG_PATH/bin/etcd.sh

install -m 755 /pkg/extra/etcdctl/dcos_etcdctl.py $PKG_PATH/bin/dcos-etcdctl

# Auto-start the dcos-etcd service on the masters.
mkdir -p "$PKG_PATH/dcos.target.wants_master"
cp /pkg/extra/systemd/dcos-etcd.service "$PKG_PATH/dcos.target.wants_master/dcos-etcd.service"
