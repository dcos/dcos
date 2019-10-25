#!/bin/sh
set -o nounset -o errexit

# Get the IP address of the interface specified by $1
get_ip_from_interface()
{
  ip -6 addr show $1 | grep "scope global" | awk -F '[ \t]+|/' '{print $3}'
}

get_ip_from_interface eth0
