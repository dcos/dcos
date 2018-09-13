#!/bin/bash
set -o errexit -o nounset -o pipefail

echo ">>> In install_dcos_required_packages.sh:"

# Install packages required by DC/OS

: ${ROOTFS:?"ERROR: ROOTFS must be set"}

if [ ! -d "${ROOTFS}/etc/yum.repos.d" ]; then
    cp -r /etc/yum.repos.d "${ROOTFS}/etc"
fi

yum --installroot="${ROOTFS}" -t -y install \
  perl \
  tar \
  xz \
  unzip \
  curl \
  bind-utils \
  net-tools \
  ipset \
  libtool-ltdl \
  rsync \
  nfs-utils \
  wget \
  git
