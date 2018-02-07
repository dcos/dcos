#!/bin/bash

set -e

FAULT_DOMAIN_SCRIPT=/opt/mesosphere/bin/detect_fault_domain

if [ -x $FAULT_DOMAIN_SCRIPT ]; then
  export MESOS_DOMAIN="$($FAULT_DOMAIN_SCRIPT)"
fi

function coreos_networkd_config() {
 network_config="/etc/systemd/network/dcos.network"
 sudo tee $network_config > /dev/null<<'EOF'
 [Match]
  Type=bridge
  Name=docker* m-* d-* vtep*
 
 [Link]
  Unmanaged=yes
EOF
}

distro="$(source /etc/os-release && echo "${ID}")"
if [[ "${distro}" == 'coreos' ]]; then
     if systemctl list-unit-files | grep systemd-networkd.service > /dev/null; then
       coreos_networkd_config
 
       if systemctl is-enabled systemd-networkd > /dev/null; then
          sudo systemctl restart systemd-networkd
       fi
    fi
fi  

exec "$@"
