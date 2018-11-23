#!/usr/bin/env bash

set -xe

myip=`/opt/mesosphere/bin/detect_ip`
nodes=`cat /run/dcos/cockroach/nodes`

exec /opt/mesosphere/active/cockroach/bin/cockroach start \
     --logtostderr \
     --cache=100MiB \
     --store=/var/lib/dcos/cockroach \
     --insecure \
     --advertise-host=${myip} \
     --host=${myip} \
     --port=26257 \
     --http-host=127.0.0.1 \
     --http-port=8090 \
     --log-dir= \
     --pid-file=/run/dcos/cockroach/cockroach.pid \
     --join=${nodes}
