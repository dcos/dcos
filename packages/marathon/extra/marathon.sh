#!/bin/bash
set -euo pipefail

LIBPROCESS_IP=$($MESOS_IP_DISCOVERY_COMMAND)
MARATHON_HOSTNAME="$LIBPROCESS_IP"

# We only set this field if the old, deprecated one hasn't already been customized by some other means
# Don't remove until Marathon 1.11, so that DC/OS users have a chance to see an error message with Marathon 1.10

# If DefaultAcceptedResourceRoles is not set, then we try to assign a default value to resource roles
# default behavior
if [ -z "${MARATHON_DEFAULT_ACCEPTED_RESOURCE_ROLES+x}" ]; then
    : ${MARATHON_ACCEPTED_RESOURCE_ROLES_DEFAULT_BEHAVIOR="unreserved"}
fi

if [ -z "${MARATHON_DISABLE_ZK_COMPRESSION+x}" ]; then
  MARATHON_ZK_COMPRESSION=""
fi

if [ -z "${MARATHON_DISABLE_REVIVE_OFFERS_FOR_NEW_APPS+x}" ]; then
  MARATHON_REVIVE_OFFERS_FOR_NEW_APPS=""
fi


$PKG_PATH/marathon/bin/marathon \
    -Duser.dir=/var/lib/dcos/marathon \
    -J-server \
    -J-verbose:gc \
    -J-XX:+PrintGCDetails \
    -J-XX:+PrintGCTimeStamps \
    --master zk://zk-1.zk:2181,zk-2.zk:2181,zk-3.zk:2181,zk-4.zk:2181,zk-5.zk:2181/mesos \
    --mesos_leader_ui_url "/mesos" \
    --metrics_statsd --metrics_statsd_host "$STATSD_UDP_HOST" --metrics_statsd_port "$STATSD_UDP_PORT"
