#!/bin/bash
set -o errexit -o nounset -o pipefail

# Run from a CentOS or RHEL instance on AWS with a secondary 8GB EBS volume
# ($DEVICE) attached to create a fresh installation of CentOS7 on $DEVICE.

# When complete, convert the $DEVICE into an AMI by creating a snapshot of the
# EBS volume and converting the snapshot into an AMI.  These steps can be done
# with the AWS web console or using the CLI tools.

: ${DEVICE:?"ERROR: DEVICE must be set"}

OS_VERSION=7-4.1708.el7.centos
OS_VERSION_SHORT=7.4.1708

ROOTFS=/rootfs

export DEVICE
export ROOTFS

# Create and mount a rootfs volume to build a system on
. lib/create_and_mount_rootfs.sh

# Initialize rootfs RPM database
rpm --root="$ROOTFS" --initdb
rpm --root="$ROOTFS" -ivh \
    http://mirrors.kernel.org/centos/"${OS_VERSION_SHORT}"/os/x86_64/Packages/centos-release-"${OS_VERSION}".x86_64.rpm

# Install base packages
. lib/install_base_packages.sh

# Configure host networking
. lib/configure_networking.sh

# Configure system clock, mounts, etc
. lib/configure_system.sh

# Configure grub on the rootfs volume
. lib/configure_grub.sh

# Bootstrap cloudinit configuration
cp cloud.cfg "${ROOTFS}/etc/cloud/cloud.cfg"

# Configure services
. lib/configure_services.sh

# Clean up and unmount the rootfs volume
umount -AR "${ROOTFS}"
