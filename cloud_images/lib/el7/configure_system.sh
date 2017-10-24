#!/bin/bash
set -o errexit -o nounset -o pipefail

# Configure system clock, mounts, etc

: ${ROOTFS:?"ERROR: ROOTFS must be set"}

cp -a /etc/skel/.bash* "${ROOTFS}/root"

cp /usr/share/zoneinfo/UTC "${ROOTFS}/etc/localtime"
echo 'ZONE="UTC"' > "${ROOTFS}/etc/sysconfig/clock"

cat > "${ROOTFS}/etc/fstab" << END
LABEL=root / xfs defaults 0 0
END

echo 'RUN_FIRSTBOOT=NO' > "${ROOTFS}/etc/sysconfig/firstboot"

BINDMNTS="dev sys etc/hosts etc/resolv.conf"
for d in ${BINDMNTS} ; do
  mount --bind "/${d}" "${ROOTFS}/${d}"
done
mount -t proc none "${ROOTFS}/proc"
