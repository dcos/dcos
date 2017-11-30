#!/bin/bash
set -o errexit -o nounset -o pipefail

# Install base packages

: ${ROOTFS:?"ERROR: ROOTFS must be set"}

cp -r /etc/yum.repos.d "${ROOTFS}/etc"

yum --installroot="${ROOTFS}" --nogpgcheck -t -y groupinstall core
yum --installroot="${ROOTFS}" --nogpgcheck -t -y install openssh-server grub2 tuned kernel chrony
yum --installroot="${ROOTFS}" --nogpgcheck -t -y install cloud-init cloud-utils-growpart

yum --installroot="${ROOTFS}" -C -t -y remove NetworkManager firewalld --setopt="clean_requirements_on_remove=1"
