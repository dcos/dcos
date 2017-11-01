#!/bin/bash
set -o errexit -o nounset -o pipefail

# Install packages required by DC/OS

: ${ROOTFS:?"ERROR: ROOTFS must be set"}

cp -r /etc/yum.repos.d "${ROOTFS}/etc"

yum --installroot="${ROOTFS}" --nogpgcheck -t -y install \
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
	nfs-utils
