#!/bin/bash
set -euo pipefail

export LIBPROCESS_IP=$($MESOS_IP_DISCOVERY_COMMAND)

# Assign values to env VARS if they are not set already
: ${MARATHON_HOSTNAME="$LIBPROCESS_IP"}
: ${MARATHON_MESOS_ROLE="slave_public"}
: ${MARATHON_MAX_INSTANCES_PER_OFFER=100}
: ${MARATHON_TASK_LAUNCH_CONFIRM_TIMEOUT=1800000}
: ${MARATHON_TASK_LAUNCH_TIMEOUT=86400000}
: ${MARATHON_TASK_RESERVATION_TIMEOUT=1800000}
: ${MARATHON_DECLINE_OFFER_DURATION=300000}
: ${STATSD_UDP_HOST="localhost"}
: ${STATSD_UDP_PORT="61825"}
: ${MARATHON_ENABLE_FEATURES="vips,task_killing,external_volumes,gpu_resources"}
: ${MARATHON_MESOS_AUTHENTICATION_PRINCIPAL="dcos_marathon"}
: ${MARATHON_MESOS_USER="root"}

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


export JAVA_OPTS="${MARATHON_JAVA_ARGS-}"
export -n MARATHON_JAVA_ARGS
export \
  MARATHON_DECLINE_OFFER_DURATION \
  MARATHON_ENABLE_FEATURES \
  MARATHON_HOSTNAME \
  MARATHON_MAX_INSTANCES_PER_OFFER \
  MARATHON_MESOS_AUTHENTICATION_PRINCIPAL \
  MARATHON_MESOS_ROLE \
  MARATHON_MESOS_USER \
  MARATHON_REVIVE_OFFERS_FOR_NEW_APPS \
  MARATHON_TASK_LAUNCH_CONFIRM_TIMEOUT \
  MARATHON_TASK_LAUNCH_TIMEOUT \
  MARATHON_TASK_RESERVATION_TIMEOUT \
  STATSD_UDP_HOST \
  STATSD_UDP_PORT \
  MARATHON_ZK_COMPRESSION \
  MARATHON_ACCEPTED_RESOURCE_ROLES_DEFAULT_BEHAVIOR \
  MARATHON_DEFAULT_ACCEPTED_RESOURCE_ROLES

exec $PKG_PATH/marathon/bin/marathon \
    -Duser.dir=/var/lib/dcos/marathon \
    -J-server \
    -J-verbose:gc \
    -J-XX:+PrintGCDetails \
    -J-XX:+PrintGCTimeStamps \
    --master zk://zk-1.zk:2181,zk-2.zk:2181,zk-3.zk:2181,zk-4.zk:2181,zk-5.zk:2181/mesos \
    --mesos_leader_ui_url "/mesos" \
    --metrics_statsd --metrics_statsd_host "$STATSD_UDP_HOST" --metrics_statsd_port "$STATSD_UDP_PORT"
