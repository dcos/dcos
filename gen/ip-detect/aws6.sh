#!/bin/sh
set -o nounset -o errexit

# Get the IP address of the interface specified by $1
get_private_ip_from_metaserver()
{
    MAC=$(ip addr show dev $1 | awk '/ether/ {print $2}')
    curl -fsSL http://169.254.169.254/latest/meta-data/network/interfaces/macs/$MAC/ipv6s
}

get_private_ip_from_metaserver eth0
