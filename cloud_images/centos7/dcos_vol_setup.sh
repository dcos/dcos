#!/bin/bash
set -o errexit -o nounset -o pipefail

export device=${1:-}
export mount_location=${2:-}

function usage {
cat <<USAGE
 USAGE: $(basename "$0") <device> <mount_location>

  This script will partition, format, and persistently mount the device to the specified location.
  It is intended to run as an early systemd unit (local-fs-pre.target) on AWS to set up EBS volumes.
  It will only execute if <device> is not yet partitioned.

 EXAMPLES:

  $(basename "$0") /dev/xvde /dcos/volume1

USAGE
}

for i in "$@"
do
  case "$i" in                                      # Munging globals, beware
    -h|--help)                usage                 ;;
    --)                       break                 ;;
    *)                        # unknown option      ;;
  esac
done

function main {
  if [[ -z "$mount_location" || -z "$device" ]]
  then
    usage
    exit 1
  fi

  partition=${device}1
  if [[ ! -b "$partition" ]]
  then
    echo "Partition $partition not detected: creating partitions"
    parted -s -a optimal "$device" -- \
      mklabel gpt \
      mkpart primary xfs 1 -1
    partprobe "$device"
    echo "Formatting: $partition"
    mkfs.xfs "$partition" >/dev/null
    echo "Setting up partition mount"
    mkdir -p "$mount_location"
    fstab="$partition $mount_location xfs defaults,nofail 0 2"
    echo "Adding entry to fstab: $fstab"
    echo "$fstab" >> /etc/fstab
    echo "Mounting: $partition to $mount_location"
    mount -a
  else
    echo "Partition $partition detected: no action taken"
    exit
  fi
}

if [[ ${1:-} ]] && declare -F | cut -d' ' -f3 | fgrep -qx -- "${1:-}"
then "$@"
else main "$@"
fi
