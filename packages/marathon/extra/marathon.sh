#!/bin/bash
set -euo pipefail

export HOST_IP=$($MESOS_IP_DISCOVERY_COMMAND)
export MARATHON_HOSTNAME=$HOST_IP
export LIBPROCESS_IP=$HOST_IP

JAVA_ARGS=

EXTRA_ARGS="${MARATHON_EXTRA_ARGS-} --mesos_user ${MESOS_USER} --mesos_authentication_principal dcos_marathon"
if [ "${MESOS_FRAMEWORK_AUTHN-}" = "true" ]; then
    EXTRA_ARGS="${EXTRA_ARGS} --mesos_authentication"
fi

export -n MARATHON_EXTRA_ARGS
exec $PKG_PATH/marathon/bin/marathon \
    -Duser.dir=/var/lib/dcos/marathon \
    -J-server \
    -J-verbose:gc \
    -J-XX:+PrintGCDetails \
    -J-XX:+PrintGCTimeStamps \
    --master $MARATHON_MESOS_MASTER_URL \
    --default_accepted_resource_roles "*" \
    --mesos_role "slave_public" \
    --max_instances_per_offer 100 \
    --task_launch_timeout 86400000 \
    --decline_offer_duration 300000 \
    --revive_offers_for_new_apps \
    --zk_compression \
    --mesos_leader_ui_url "/mesos" \
    --enable_features "vips,task_killing,external_volumes,gpu_resources" \
    --mesos_authentication_principal "dcos_marathon" \
    --mesos_user $MARATHON_MESOS_USER
