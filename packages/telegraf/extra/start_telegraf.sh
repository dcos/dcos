#!/bin/bash

set -o errexit
set -o xtrace
set -o nounset

# Read the cluster ID.
cluster_id_file="/var/lib/dcos/cluster-id"
if [ ! -f "${cluster_id_file}" ]; then
  echo "Missing required file: ${cluster_id_file}" >&2
  exit 1
fi
cluster_id="$(cat ${cluster_id_file})"

# Export the cluster ID to an env var so telegraf config can reference it.
export DCOS_CLUSTER_ID="${cluster_id}"

# Export the IP address
export NODE_PRIVATE_IP="$(/opt/mesosphere/bin/detect_ip)"

# Start telegraf.
exec /opt/mesosphere/bin/telegraf "$@"
