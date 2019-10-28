#!/bin/sh
set -o nounset -o errexit

get_private_ip_from_metaserver()
{
    set +o errexit
    for i in `seq 1 3` ; do
        out=$(curl -fsSL http://169.254.169.254/latest/meta-data/local-ipv4 2>&1)
        if [ $? = 0 ] ; then
            echo "$out"
            return
        fi
        sleep 1
    done
    echo "$out"
}

get_private_ip_from_metaserver
