#!/bin/bash

set -e

FAULT_DOMAIN_SCRIPT=/opt/mesosphere/bin/detect_fault_domain

if [ -x $FAULT_DOMAIN_SCRIPT ]; then
  export MESOS_DOMAIN="$($FAULT_DOMAIN_SCRIPT)"
fi

exec "$@"
