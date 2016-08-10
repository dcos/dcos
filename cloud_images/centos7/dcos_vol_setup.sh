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

function configure_lvm {
  echo "Stopping docker daemon and removing /var/lib/docker"
  systemctl daemon-reload
  systemctl stop docker

  rm -rf /var/lib/docker
  echo "Creating physcial device for logical volume..."
  pvcreate -yf "$device" 

  echo "Creating volume group \"docker\""
  vgcreate docker "$device"

  echo "Creating the pool named \"thinpool\""
  lvcreate --wipesignatures y -n thinpool docker -l 95%VG
  lvcreate --wipesignatures y -n thinpoolmeta docker -l 1%VG

  echo "Converting the pool to thinpool"
  lvconvert -y --zero n -c 512K --thinpool docker/thinpool --poolmetadata docker/thinpoolmeta

  echo "Creating /etc/lvm/profile/docker-thinpool.profile"
  cat << EOF > /etc/lvm/profile/docker-thinpool.profile
activation {
    thin_pool_autoextend_threshold=80
    thin_pool_autoextend_percent=20
}
EOF

  echo "Applying logical volume changes to the system."
  lvchange -ff --metadataprofile docker-thinpool docker/thinpool

  systemctl start docker 
}

function partition_device {
  echo "Creating partition on $device from entire volume..."
  parted -s -a optimal "$device" -- \
    mklabel gpt \
    mkpart primary ext4 1 -1
  partprobe "$device"

  echo "Formatting $device to ext4 filesystem..."
  mkfs.ext4 "$device" 

  echo "Making $mount_location..."
  mkdir -p "$mount_location"
  fstab="$device $mount_location ext4 defaults,nofail 0 2" 
  
  echo "Adding entry to fstab: $fstab"
  echo "$fstab" >> /etc/fstab
  
  echo "Mounting $device to $mount_location..."
  mount -a
}

function main {
  if [[ -z "$mount_location" || -z "$device" ]]
  then
    usage
    exit 1
  fi

  if [[ $(/sbin/sfdisk -d $device 2>&1) == "" ]]
  then
    if [[ $mount_location == "/var/lib/docker" ]]; then
      configure_lvm
    else
      partition_device
    fi 
  else
    echo "Partition $device detected: no action taken"
    return
  fi
}

if [[ ${1:-} ]] && declare -F | cut -d' ' -f3 | fgrep -qx -- "${1:-}"
then "$@"
else main "$@"
fi
