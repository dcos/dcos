#!/bin/sh
set -o nounset

for i in `seq 1 3` ; do
    out=$(curl -fsSL http://169.254.169.254/latest/meta-data/public-ipv4 2>&1)
    if [ $? = 0 ] ; then
        echo "$out"
        exit 0
    fi
    sleep 1
done
echo "$out"
