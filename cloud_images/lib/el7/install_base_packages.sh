#!/bin/bash
set -o errexit -o nounset -o pipefail

# Install base packages

: ${ROOTFS:?"ERROR: ROOTFS must be set"}

cp -r /etc/yum.repos.d "${ROOTFS}/etc"

yum --installroot="${ROOTFS}" -t -y groupinstall core
yum --installroot="${ROOTFS}" -t -y install openssh-server grub2 tuned kernel chrony dracut-config-generic
yum --installroot="${ROOTFS}" -t -y install cloud-init cloud-utils-growpart

yum --installroot="${ROOTFS}" -C -t -y remove NetworkManager firewalld --setopt="clean_requirements_on_remove=1"

echo ">>> Compatibility fixes for newer AWS instances like C5 and M5, see https://bugs.centos.org/view.php?id=14107&nbn=5"
chroot "${ROOTFS}" dracut -f
