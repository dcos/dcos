#!/bin/bash
set -o errexit -o nounset -o pipefail

# Configure host networking

: ${ROOTFS:?"ERROR: ROOTFS must be set"}

cat > "${ROOTFS}/etc/hosts" << END
127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4
::1         localhost localhost.localdomain localhost6 localhost6.localdomain6
END

touch "${ROOTFS}/etc/resolv.conf"

cat > "${ROOTFS}/etc/sysconfig/network" << END
NETWORKING=yes
NETWORKING_IPV6=yes
END

cat > "${ROOTFS}/etc/sysconfig/network-scripts/ifcfg-eth0" << END
DEVICE="eth0"
BOOTPROTO="dhcp"
ONBOOT="yes"
TYPE="Ethernet"
USERCTL="yes"
PEERDNS="yes"
IPV6INIT="yes"
DHCPV6C="yes"
NM_CONTROLLED="no"
PERSISTENT_DHCLIENT="1"
END
