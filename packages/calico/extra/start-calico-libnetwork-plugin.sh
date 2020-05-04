#!/usr/bin/env bash

set -xe

# Use the detected IP instead of the hostname as the libnetwork host name,
# since felix registers under that name.
CALICO_LIBNETWORK_HOSTNAME=$(/opt/mesosphere/bin/detect_ip)

# By default libnetwork creates workload endpoints in the `libnetwork` namespace
# while the CNI plugins in the default namespace. We don't want this separation.
CALICO_LIBNETWORK_NAMESPACE=default

# Start the plugin
export CALICO_LIBNETWORK_HOSTNAME
export CALICO_LIBNETWORK_NAMESPACE
exec /opt/mesosphere/bin/calico-libnetwork-plugin
