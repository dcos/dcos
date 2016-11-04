#!/bin/bash
set -o errexit -o nounset -o pipefail

export device=${1:-}
export mount_location=${2:-}

function usage {
cat <<USAGE
 USAGE: $(basename "$0") <device> <mount_location>

  This script will format, and persistently mount the device to the specified location.
  It is intended to run as an early systemd unit (local-fs-pre.target) on AWS to set up EBS volumes.
  It will only execute if <device> doesn't already contain a filesystem.

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

  echo -n "Waiting for $device to come online"
  until test -b "$device"; do sleep 1; echo -n .; done
  echo
  local formated
  mkfs.xfs $device > /dev/null 2>&1 && formated=true || formated=false
  if [ "$formated" = true ]
  then
    echo "Setting up device mount"
    mkdir -p "$mount_location"
    fstab="$device $mount_location xfs defaults 0 2"
    echo "Adding entry to fstab: $fstab"
    echo "$fstab" >> /etc/fstab
    if [ "$mount_location" = "/var/log" ]; then
      echo "Preparing $device by migrating logs from $mount_location"
      mkdir -p /var/log-prep
      mount $device /var/log-prep
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
      echo -n "Mounting: $device to $mount_location"
      until grep ^$device /etc/mtab > /dev/null; do sleep 1; echo -n .; mount "$mount_location"; done
      echo
      systemctl restart systemd-journald || :
      systemctl is-enabled tuned > /dev/null && systemctl start tuned || :
      systemctl is-enabled chronyd > /dev/null && systemctl start chronyd || :
    else
      echo -n "Mounting: $device to $mount_location"
      until grep ^$device /etc/mtab > /dev/null; do sleep 1; echo -n .; mount "$mount_location"; done
      echo
    fi
  else
    echo "Device $device contains a filesystem: no action taken"
    exit
  fi
}

if [[ ${1:-} ]] && declare -F | cut -d' ' -f3 | fgrep -qx -- "${1:-}"
then "$@"
else main "$@"
fi
