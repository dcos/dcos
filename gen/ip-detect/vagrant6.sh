#!/usr/bin/env bash
set -o nounset -o errexit

# Get COREOS COREOS_PRIVATE_IPV6
if [ -e /etc/environment ]
then
  set -o allexport
  source /etc/environment
  set +o allexport
fi


get_defaultish_ip()
{
    ipv6=$(ip -6 route get 2001:4860:4860::8888 | awk '{print $9; exit}')
    echo $ipv6
}

echo ${COREOS_PRIVATE_IPV6:-$(get_defaultish_ip)}
