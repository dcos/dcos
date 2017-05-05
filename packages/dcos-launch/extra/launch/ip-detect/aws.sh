#!/bin/sh
set -o nounset -o errexit

# Get COREOS COREOS_PRIVATE_IPV4
if [ -e /etc/environment ]
then
  set -o allexport
  source /etc/environment
  set +o allexport
fi

get_private_ip_from_metaserver()
{
    curl -fsSL http://169.254.169.254/latest/meta-data/local-ipv4
}

echo ${COREOS_PRIVATE_IPV4:-$(get_private_ip_from_metaserver)}
