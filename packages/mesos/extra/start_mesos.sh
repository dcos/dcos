#!/bin/bash

set -e

SRC="/opt/mesosphere/etc/dcos.network"
DST="/etc/systemd/network/dcos.network"

function cmp_and_update {
    cmp --silent $1 $2 || (cp $1 $2 && false)
}

distro="$(source /etc/os-release && echo "${ID}")"
if [[ "${distro}" == 'coreos' ]]; then
     if systemctl list-unit-files | grep systemd-networkd.service > /dev/null; then
       echo "Configuring systemd-networkd to ignore docker bridge and DC/OS overlay interfaces..."
       if [ ! -f $SRC ]; then
           echo "Quiting.. $SRC file not found"
           exit 1
       fi

       if cmp_and_update $SRC $DST; then
           echo "Skipping restart of systemd-networkd..."
       elif systemctl is-active systemd-networkd > /dev/null; then
          echo "Restarting systemd-networkd"
          sudo systemctl restart systemd-networkd
       fi
    fi
fi

exec "$@"
