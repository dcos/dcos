#!/bin/sh
set -o nounset -o errexit

# Get the IP address of the interface specified by $1
get_private_ip_from_metaserver()
{
    MAC=$(ip addr show dev $1 | awk '/ether/ {print $2}')
    set +o errexit
    for i in `seq 1 3` ; do
        out=$(curl -fsSL http://169.254.169.254/latest/meta-data/network/interfaces/macs/$MAC/ipv6s)
        if [ $? = 0 ] ; then
            echo "$out"
            return
        fi
        sleep 1
    done
    echo "$out"
    
}

get_private_ip_from_metaserver eth0
