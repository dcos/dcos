#!/bin/bash
set -o errexit -o nounset -o pipefail

# Configure services

: ${ROOTFS:?"ERROR: ROOTFS must be set"}

chroot "${ROOTFS}" systemctl enable sshd.service
chroot "${ROOTFS}" systemctl enable cloud-init.service
chroot "${ROOTFS}" systemctl enable chronyd.service
chroot "${ROOTFS}" systemctl mask tmp.mount
chroot "${ROOTFS}" systemctl set-default multi-user.target
