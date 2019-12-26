#!/usr/bin/env bash

set -xe

DEFAULT_PROFILE_NAME="calico"
NODENAME_FILE='/var/lib/calico/nodename'
export NODENAME=`/opt/mesosphere/bin/detect_ip`
export IP=`/opt/mesosphere/bin/detect_ip`

mkdir -p /etc/calico
mkdir -p /var/lib/calico

cp /opt/mesosphere/etc/calico/calicoctl.cfg /etc/calico/calicoctl.cfg
cp /opt/mesosphere/active/calico/etc/profile.yaml /var/lib/calico/profile.yaml

# /var/lib/calico/nodename is used to determine whether or not the current node
# has been initialized.
# the default calico profile is created only:
# 1. current calico node is not intialized
# 2. calico profile does not exist
# FIXME: we assume that calico profile will not be deleted, otherwise adding or
# replacing a new node will create a default profile when calico profile does
# not exist.
if [ ! -f $NODENAME_FILE ]; then
	/opt/mesosphere/bin/calicoctl get profile $DEFAULT_PROFILE_NAME || /opt/mesosphere/bin/calicoctl apply -f /var/lib/calico/profile.yaml
fi

# initialize a calico node and network devices.
# reference:
# https://github.com/projectcalico/node/blob/master/filesystem/etc/rc.local
echo $NODENAME > $NODENAME_FILE
/opt/mesosphere/bin/calico-node -startup
/opt/mesosphere/bin/calico-node -allocate-tunnel-addrs

# we need to translate environment variables into the ones used by felix.
# reference:
# https://github.com/projectcalico/node/blob/master/filesystem/etc/service/available/felix/run

# Felix doesn't understand NODENAME, but the container exports it as a common
# interface. This ensures Felix gets the right name for the node.
if [ ! -z $NODENAME ]; then
    export FELIX_FELIXHOSTNAME=$NODENAME
fi
export FELIX_ETCDADDR=$ETCD_AUTHORITY
export FELIX_ETCDENDPOINTS=$ETCD_ENDPOINTS
export FELIX_ETCDSCHEME=$ETCD_SCHEME
export FELIX_ETCDCAFILE=$ETCD_CA_CERT_FILE
export FELIX_ETCDKEYFILE=$ETCD_KEY_FILE
export FELIX_ETCDCERTFILE=$ETCD_CERT_FILE
if [ ! -z $DATASTORE_TYPE ]; then
    export FELIX_DATASTORETYPE=$DATASTORE_TYPE
fi
/opt/mesosphere/bin/calico-node -felix
