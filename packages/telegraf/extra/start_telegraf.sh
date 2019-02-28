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

# Retrieve the node's private IP address.
node_private_ip=$(/opt/mesosphere/bin/detect_ip)

# Export values to env vars so Telegraf config can reference them.
export DCOS_CLUSTER_ID="${cluster_id}"
export DCOS_NODE_PRIVATE_IP="${node_private_ip}"

# Retrieve the fault domain for this machine
fault_domain_script="/opt/mesosphere/bin/detect_fault_domain"
fault_domain_extractor="$(pwd)/tools/extract_fault_domain.py"

if [ -x $fault_domain_script ]; then
  # If a fault domain script exists, export environment variables so that
  # fault_domain_zone and fault_domain_region are added to all tags originating
  # in this machine
  eval `$(fault_domain_script) | $(fault_domain_extractor)`
fi

# Create containers dir for dcos_statsd input.
mkdir -p "${TELEGRAF_CONTAINERS_DIR}"
# Migrate old containers dir to new location in case the cluster was upgraded.
/opt/mesosphere/active/telegraf/tools/migrate_containers_dir.sh "${LEGACY_CONTAINERS_DIR}" "${TELEGRAF_CONTAINERS_DIR}"

# Ensure that old socket file is removed, if present
# TODO(philipnrmn): investigate whether moving to a systemd-managed socket
# would be a better solution than manually creating and removing this file.
rm -f /run/dcos/telegraf/dcos_statsd.sock
# Start telegraf.
exec /opt/mesosphere/bin/telegraf "$@"
