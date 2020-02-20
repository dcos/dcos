#!/usr/bin/env bash

set -xe

IP_PRIVATE=$($MESOS_IP_DISCOVERY_COMMAND)
CLUSTER_NODES=`cat /run/dcos/etcd/initial-nodes`
CLUSTER_STATE=`cat /run/dcos/etcd/initial-state`

GOMAXPROCS=$(nproc)

exec /opt/mesosphere/active/etcd/bin/etcd \
     --name "etcd-${IP_PRIVATE}" \
     --data-dir /var/lib/dcos/etcd/default.etcd/ \
     --listen-peer-urls "https://${IP_PRIVATE}:2380" \
     --listen-client-urls "${PROTOCOL}://${IP_PRIVATE}:2379,${PROTOCOL}://localhost:2379" \
     --initial-advertise-peer-urls "https://${IP_PRIVATE}:2380" \
     --initial-cluster $CLUSTER_NODES \
     --initial-cluster-state $CLUSTER_STATE \
     --initial-cluster-token "etcd-dcos" \
     --advertise-client-urls "${PROTOCOL}://${IP_PRIVATE}:2379,${PROTOCOL}://localhost:2379" \
     --enable-v2=true
