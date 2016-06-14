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

function ensure_lvm_installed {
  which lvm
  if $? -ne 0; then
    echo "Installing LVM2..."
    yum install -y lvm2*
  else
    echo "LVM2 installed."
  fi
}

function create_partition {
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
      mkpart primary ext4 1 -1
    partprobe "$device"
    echo "Formatting: $partition"
    mkfs.ext4 "$partition" >/dev/null
    echo "Setting up partition mount"
    mkdir -p "$mount_location"
    fstab="$partition $mount_location ext4 defaults,nofail 0 2" 
    echo "Adding entry to fstab: $fstab"
    echo "$fstab" >> /etc/fstab
    echo "Mounting: $partition to $mount_location"
    mount -a
  else
    echo "Partition $partition detected: no action taken"
    exit
  fi
}

function create_thinpool_volume {
  echo "Ensureing LVM2 is installed."
  ensure_lvm_installed
  # init a physical vol for the LVM 
  pvcreate /dev/xvdf
  
  # create the docker volume group
  echo "Creating volume group \"docker\""
  vgcreate docker /dev/xvdf
  
  # Create thinpool named thinpool
  echo "Creating the thinpool named \"thinpool\""
  lvcreate --wipesignatures y -n thinpool docker -l 95%VG
  lvcreate --wipesignatures y -n thinpoolmeta docker -l 1%VG
  
  # convert the pool to thinpool
  echo "Converting the pool to thinpool"
  lvconvert -y --zero n -c 512K --thinpool docker/thinpool --poolmetadata docker/thinpoolmeta
  
  echo "Creating /etc/lvm/profile/docker-thinpool.profile"
  cat << EOF > /etc/lvm/profile/docker-thinpool.profile
activation {
    thin_pool_autoextend_threshold=80
    thin_pool_autoextend_percent=20
}
  EOF

  # Apply the profile created above
  echo "Applying LVM changes to the system."
  lvchange --metadataprofile docker-thinpool docker/thinpool
  
  echo "Done creating logical volume"
}

if [[ ${1:-} ]] && declare -F | cut -d' ' -f3 | fgrep -qx -- "${1:-}"
then "$@"
else 
  create_partition && \
  create_thinpool_volume "$@"
fi
