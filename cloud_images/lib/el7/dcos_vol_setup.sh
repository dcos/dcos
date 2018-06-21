#!/bin/bash
set -o errexit -o nounset -o pipefail

# Avoid getting killed due to https://bugs.freedesktop.org/show_bug.cgi?id=84923 if
# systemd-journald is restarted while we are running.
trap '' PIPE

export device=${1:-}
export mount_location=${2:-}
export label=$(echo ${mount_location:1:12} | sed 's/\//-/g')

function usage {
cat <<EOUSAGE
USAGE: $(basename "$0") <device> <mount_location>

 This script will format, and persistently mount the device to the specified
 location. It is intended to run as an early systemd unit (local-fs-pre.target)
 on AWS to set up EBS volumes. If a device cant be found for 5 secons, it is simple skipped.

 If <mount_location> is /var/log the script will migrate existing data to the
 new filesystem.

 It will only execute if <device> doesn't already contain a filesystem.

EXAMPLES:

 $(basename "$0") /dev/xvde /dcos/volume1

EOUSAGE
}

# Try to be resilient to SIGPIPE, incase anyone restarts journald while we are running.
function noncritical {
  set +e; ${*}; set -e
}

function checked_mount() {
  local dev="$1"
  local location="$2"
  noncritical echo -n "Mounting: $dev to $location"
  until grep "^$dev" /etc/mtab > /dev/null; do
    noncritical sleep 1
    noncritical echo -n .
    # mount might think the device is already mounted, so accept nonzero exit status
    mount "$location" || :
  done
  noncritical echo
}

for i in "$@"
do
  case "$i" in                                      # Munging globals, beware
    -h|--help)                noncritical usage     ;;
    --)                       break                 ;;
    *)                        # unknown option      ;;
  esac
done

function main {
  if [[ -z "$mount_location" || -z "$device" ]]
  then
    noncritical usage
    exit 1
  fi

  noncritical echo -n "Waiting for $device to come online"
  retry=5
  until test -b "$device"; do
    noncritical sleep 1; noncritical echo -n .;
    let retry=retry-1
    if [ $retry -eq 0 ]; then
     noncritical exit 0
    fi
  done
  noncritical echo
  local formated
  mkfs.xfs -n ftype=1 -L ${label} $device > /dev/null 2>&1 && formated=true || formated=false
  if [ "$formated" = true ]
  then
    noncritical echo "Setting up device mount"
    mkdir -p "$mount_location"
    fstab="LABEL=${label} $mount_location xfs defaults 0 2"
    noncritical echo "Adding entry to fstab: $fstab"
    echo "$fstab" >> /etc/fstab
    if [ "$mount_location" = "/var/log" ]; then
      noncritical echo "Preparing $device by migrating logs from $mount_location"
      mkdir -p /var/log-prep
      mount "$device" /var/log-prep
      mkdir -p /var/log-prep/journal
      cp -a /var/log/. /var/log-prep/
      umount /var/log-prep
      rmdir /var/log-prep
      rm -rf /var/log
      mkdir -p /var/log
      checked_mount "$device" "$mount_location"
      systemd-tmpfiles --create --prefix /var/log/journal
      systemctl kill --signal=SIGUSR1 systemd-journald
    else
      checked_mount "$device" "$mount_location"
    fi
  else
    noncritical echo "Device $device contains a filesystem: no action taken"
    noncritical exit 0
  fi
}

if [[ ${1:-} ]] && declare -F | cut -d' ' -f3 | fgrep -qx -- "${1:-}"
then "$@"
else main "$@"
fi
