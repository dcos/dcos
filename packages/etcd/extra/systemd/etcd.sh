#!/usr/bin/env bash

set -xe

IP_PRIVATE=`/opt/mesosphere/bin/detect_ip`
CLUSTER_NODES=`cat /var/lib/dcos/etcd/initial-nodes`
CLUSTER_STATE=`cat /var/lib/dcos/etcd/initial-state`

GOMAXPROCS=$(nproc)

exec /opt/mesosphere/active/etcd/bin/etcd \
     --name "etcd-${IP_PRIVATE}" \
     --data-dir /var/lib/dcos/etcd/default.etcd/ \
     --auto-tls --peer-auto-tls \
     --listen-peer-urls "https://${IP_PRIVATE}:2380" \
     --listen-client-urls "http://${IP_PRIVATE}:2379,http://localhost:2379" \
     --initial-advertise-peer-urls "https://${IP_PRIVATE}:2380" \
     --initial-cluster $CLUSTER_NODES \
     --initial-cluster-state $CLUSTER_STATE \
     --initial-cluster-token "etcd-dcos" \
     --advertise-client-urls "http://${IP_PRIVATE}:2379,http://localhost:2379" \
     --enable-v2=true

