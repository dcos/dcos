#!/usr/bin/env bash
set -o nounset -o errexit

# Get COREOS COREOS_PRIVATE_IPV4
if [ -e /etc/environment ]
then
  set -o allexport
  source /etc/environment
  set +o allexport
fi


get_defaultish_ip()
{
    local ipv4=$(ip route get 8.8.8.8 | awk '{ for(i=1; i<NF; i++) { if($i == "src") {print $(i+1); exit} } }')
    echo $ipv4
}

echo ${COREOS_PRIVATE_IPV4:-$(get_defaultish_ip)}
