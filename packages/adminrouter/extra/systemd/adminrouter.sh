#!/bin/bash
set -euo pipefail

# Based on:
# https://lists.freedesktop.org/archives/systemd-devel/2012-October/007289.html
export HOST_IP=$($MESOS_IP_DISCOVERY_COMMAND)

exec $PKG_PATH/nginx/sbin/nginx "$@"
