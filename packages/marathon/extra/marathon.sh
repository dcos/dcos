#!/bin/bash
set -euo pipefail

export HOST_IP=$($MESOS_IP_DISCOVERY_COMMAND)
export MARATHON_HOSTNAME=$HOST_IP
export LIBPROCESS_IP=$HOST_IP

MARATHON_EXTRA_ARGS="${MARATHON_EXTRA_ARGS-}"

exec $PKG_PATH/marathon/bin/marathon \
    -Duser.dir=$MARATHON_USER_DIR \
    $MARATHON_JVM_ARGS \
    --master $MARATHON_MESOS_MASTER_URL \
    --default_accepted_resource_roles $MARATHON_ACCEPTED_ROLES \
    --mesos_role $MARATHON_MESOS_ROLE \
    --max_instances_per_offer $MARATHON_MAX_INSTANCES_PER_OFFER \
    --task_launch_timeout $MARATHON_TASK_LAUNCH_TIMEOUT \
    --decline_offer_duration $MARATHON_DECLINE_OFFER_DURATION \
    --revive_offers_for_new_apps \
    --zk_compression \
    --mesos_leader_ui_url $MARATHON_LEADER_UI_URL \
    --enable_features $MARATHON_FEATURES \
    --mesos_authentication_principal $MARATHON_PRINCIPAL \
    --mesos_user $MARATHON_MESOS_USER \
    $MARATHON_EXTRA_ARGS
