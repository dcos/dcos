#!/bin/sh
set -o nounset -o errexit

# Get COREOS COREOS_PRIVATE_IPV6
if [ -e /etc/environment ]
then
  set -o allexport
  . /etc/environment
  set +o allexport
fi

# Get the IP address of the interface specified by $1
get_ip_from_interface()
{
  ip -6 addr show $1 | grep "scope global" | awk -F '[ \t]+|/' '{print $3}'
}

echo ${COREOS_PRIVATE_IPV6:-$(get_ip_from_interface eth0)}
