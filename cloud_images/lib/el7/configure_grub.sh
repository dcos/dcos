#!/bin/bash
set -o errexit -o nounset -o pipefail

# Configure grub on the rootfs volume

: ${DEVICE:?"ERROR: DEVICE must be set"}
: ${ROOTFS:?"ERROR: ROOTFS must be set"}

cat > "${ROOTFS}/etc/default/grub" << END
GRUB_TIMEOUT=1
GRUB_DISTRIBUTOR="$(sed 's, release .*$,,g' /etc/system-release)"
GRUB_DEFAULT=saved
GRUB_DISABLE_SUBMENU=true
GRUB_TERMINAL="serial console"
GRUB_SERIAL_COMMAND="serial --speed=115200"
GRUB_CMDLINE_LINUX="console=tty0 crashkernel=auto console=ttyS0,115200 net.ifnames=0 biosdevname=0 scsi_mod.use_blk_mq=Y dm_mod.use_blk_mq=y"
GRUB_DISABLE_RECOVERY="true"
END

chroot "${ROOTFS}" grub2-mkconfig -o /boot/grub2/grub.cfg
chroot "${ROOTFS}" grub2-install "${DEVICE}"
