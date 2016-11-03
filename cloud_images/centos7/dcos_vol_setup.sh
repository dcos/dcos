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

  echo "Waiting for $device to come online"
  until test -b "$device"; do sleep 1; done
  partition=${device}1
  if [[ ! -b "$partition" ]]
  then
    echo "Partition $partition not detected: creating partitions"
    parted -s -a optimal "$device" -- \
      mklabel gpt \
      mkpart primary xfs 1 -1
    partprobe "$device" > /dev/null 2>&1 || :
    echo "Waiting for $partition to be detected by the Kernel"
    until test -b "$partition"; do sleep 1; done
    echo "Formatting: $partition"
    mkfs.xfs "$partition" > /dev/null
    echo "Setting up partition mount"
    mkdir -p "$mount_location"
    fstab="$partition $mount_location xfs defaults 0 2"
    echo "Adding entry to fstab: $fstab"
    echo "$fstab" >> /etc/fstab
    if [ "$mount_location" = "/var/log" ]; then
      echo "Preparing $partition by migrating logs from $mount_location"
      mkdir -p /var/log-prep
      mount "$partition" /var/log-prep
      mkdir -p /var/log-prep/journal
      systemctl is-active chronyd > /dev/null && systemctl stop chronyd || :
      systemctl is-active tuned > /dev/null && systemctl stop tuned || :
      # rsyslog shouldn't be active but in case it is stop it as well
      systemctl is-active rsyslog > /dev/null && systemctl stop rsyslog || :
      cp -a /var/log/. /var/log-prep/
      umount /var/log-prep
      rmdir /var/log-prep
      rm -rf /var/log
      mkdir -p /var/log
      echo "Mounting: $partition to $mount_location"
      until grep ^$partition /etc/mtab > /dev/null; do sleep 1; mount "$mount_location"; done
      systemctl restart systemd-journald || :
      systemctl is-enabled tuned > /dev/null && systemctl start tuned || :
      systemctl is-enabled chronyd > /dev/null && systemctl start chronyd || :
    else
      echo "Mounting: $partition to $mount_location"
      until grep ^$partition /etc/mtab > /dev/null; do sleep 1; mount "$mount_location"; done
    fi
  else
    echo "Partition $partition detected: no action taken"
    exit
  fi
}

if [[ ${1:-} ]] && declare -F | cut -d' ' -f3 | fgrep -qx -- "${1:-}"
then "$@"
else main "$@"
fi
