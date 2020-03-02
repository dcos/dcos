#!/bin/bash
set -euo pipefail
set -a

TLS_ENABLED=${TLS_ENABLED:-false}
LIBPROCESS_IP=$($MESOS_IP_DISCOVERY_COMMAND)
MARATHON_HOSTNAME="$LIBPROCESS_IP"
# We only set this field if the old, deprecated one hasn't already been customized by some other means
# Don't remove until Marathon 1.11, so that DC/OS users have a chance to see an error message with Marathon 1.10

# If DefaultAcceptedResourceRoles is not set, then we try to assign a default value to resource roles
# default behavior
if [ -z "${MARATHON_DEFAULT_ACCEPTED_RESOURCE_ROLES+x}" ]; then
    MARATHON_ACCEPTED_RESOURCE_ROLES_DEFAULT_BEHAVIOR="unreserved"
fi

if [ -z "${MARATHON_DISABLE_ZK_COMPRESSION+x}" ]; then
    MARATHON_ZK_COMPRESSION=""
fi

if [ -z "${MARATHON_DISABLE_REVIVE_OFFERS_FOR_NEW_APPS+x}" ]; then
    MARATHON_REVIVE_OFFERS_FOR_NEW_APPS=""
fi

if [ "${TLS_ENABLED-}" = "true" ]; then
    JAVA_OPTS="${JAVA_OPTS} -Djavax.net.ssl.trustStore=${TLS_TRUSTSTORE}"
    MARATHON_SSL_KEYSTORE_PATH="${SSL_KEYSTORE_PATH}"
    MARATHON_SSL_KEYSTORE_PASSWORD="${SSL_KEYSTORE_PASSWORD}"
fi

if [ ! -z "$MARATHON_EXTRA_ARGS" ]; then
  cat <<-EOF 1>&2
MARATHON_EXTRA_ARGS is deprecated; if you need to specify an option, use the equivalent environment variable.

For boolean args such as --disable_http, enable with an environment variable set to an empty string:

  MARATHON_DISABLE_HTTP=

For other args, like max_instances_per_offer:

  MARATHON_MAX_INSTANCES_PER_OFFER=50
EOF
fi
export -n MARATHON_EXTRA_ARGS

if [ "${MESOS_FRAMEWORK_AUTHN-}" = "true" ] && [ -z "${MARATHON_DISABLE_MESOS_AUTHENTICATION+x}" ]; then
    MARATHON_MESOS_AUTHENTICATION=""
fi

exec $PKG_PATH/marathon/bin/marathon \
    -Djava.security.properties=/opt/mesosphere/etc/java.security \
    -Duser.dir=/var/lib/dcos/marathon \
    -J-server \
    -J-verbose:gc \
    -J-XX:+PrintGCDetails \
    -J-XX:+PrintGCTimeStamps \
    --master zk://zk-1.zk:2181,zk-2.zk:2181,zk-3.zk:2181,zk-4.zk:2181,zk-5.zk:2181/mesos \
    --mesos_leader_ui_url "/mesos" \
    --metrics_statsd --metrics_statsd_host "$STATSD_UDP_HOST" --metrics_statsd_port "$STATSD_UDP_PORT" \
    $MARATHON_EXTRA_ARGS
