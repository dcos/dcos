#!/usr/bin/env bash

set -xe

export IP=`/opt/mesosphere/bin/detect_ip`
export NODENAME=`hostname`

# the default configuration path, `/etc/calico/calicoctl.cfg`, of calicoctl is
# used to simply the interaction with Calico
/usr/bin/mkdir -p /etc/calico
/usr/bin/cp /opt/mesosphere/etc/calico/calicoctl.cfg /etc/calico/calicoctl.cfg

/opt/mesosphere/bin/calicoctl apply -f \
	/opt/mesosphere/active/calico/etc/profile.yaml

# nodename fiel name is expected to be created before starting up calico-node
mkdir -p /var/lib/calico
echo $NODENAME > /var/lib/calico/nodename

# Run the startup initialisation script.  These ensure the node is correctly
# configured to run.
/opt/mesosphere/bin/calico-node -startup || exit 1

# If possible pre-allocate any tunnel addresses.
/opt/mesosphere/bin/calico-node -allocate-tunnel-addrs || exit 1

# run felix
/opt/mesosphere/bin/calico-node -felix
