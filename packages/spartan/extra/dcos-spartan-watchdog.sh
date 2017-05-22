#!/bin/bash
LOCKFILE=/opt/mesosphere/active/spartan/spartan/bin/spartan-env
# If the file is not locked
if ! flock -n $LOCKFILE true; then
  if ! /opt/mesosphere/active/toybox/bin/toybox timeout -k 1m 1m /opt/mesosphere/active/toybox/bin/toybox host ready.spartan 198.51.100.1; then
    /opt/mesosphere/active/toybox/bin/toybox pkill -l 9 -f spartan
  fi
else
  echo "Not running watchdog, Spartan not running"
fi
