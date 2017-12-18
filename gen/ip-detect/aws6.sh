#!/bin/sh
set -o nounset -o errexit

# Get COREOS COREOS_PRIVATE_IPV6
if [ -e /etc/environment ]
then
  set -o allexport
  source /etc/environment
  set +o allexport
fi

# Get the IP address of the interface specified by $1
get_private_ip_from_metaserver()
{
    MAC=$(ip addr show dev $1 | awk '/ether/ {print $2}')
    curl -fsSL http://169.254.169.254/latest/meta-data/network/interfaces/macs/$MAC/ipv6s
}

echo ${COREOS_PRIVATE_IPV6:-$(get_private_ip_from_metaserver eth0)}
