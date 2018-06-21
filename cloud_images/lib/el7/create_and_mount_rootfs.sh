#!/bin/bash
set -o errexit -o nounset -o pipefail

# Create and mount a rootfs volume to build a system on

: ${DEVICE:?"ERROR: DEVICE must be set"}
: ${ROOTFS:?"ERROR: ROOTFS must be set"}

PARTITION="${DEVICE}1"

parted -s "${DEVICE}" -- \
  mklabel msdos \
  mkpart primary xfs 1 -1 \
  set 1 boot on

# Wait for device partition creation which happens asynchronously
while [ ! -e "${PARTITION}" ]; do sleep 1; done

mkfs.xfs -f -L root "${PARTITION}"
mkdir -p "${ROOTFS}"
mount "${PARTITION}" "${ROOTFS}"
