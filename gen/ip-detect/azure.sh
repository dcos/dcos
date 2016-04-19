#!/bin/sh
set -o nounset -o errexit

# Get COREOS COREOS_PRIVATE_IPV4
if [ -e /etc/environment ]
then
  set -o allexport
  . /etc/environment
  set +o allexport
fi

# Get the IP address of the interface specified by $1
get_ip_from_interface()
{
  /sbin/ifconfig "$1" | awk '/(inet addr)/ { print $2 }' | cut -d":" -f2 | head -1
}

echo ${COREOS_PRIVATE_IPV4:-$(get_ip_from_interface eth0)}
