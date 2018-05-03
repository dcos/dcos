#!/bin/bash

set -e

# Helper to configure `networkd` on CoreOS to ignore all DC/OS overlay interfaces.
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
       echo "Configuring systemd-networkd to ignore docker bridge and DC/OS overlay interfaces..."
       coreos_networkd_config

       if systemctl is-active systemd-networkd > /dev/null; then
          sudo systemctl restart systemd-networkd
       fi
    fi
fi

exec "$@"