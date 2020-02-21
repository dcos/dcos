#!/bin/bash
set -euo pipefail

LIBPROCESS_IP=$($MESOS_IP_DISCOVERY_COMMAND)

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

if [ "${TLS_ENABLED-}" = "true" ]; then
    JAVA_OPTS="${JAVA_OPTS} -Djavax.net.ssl.trustStore=${TLS_TRUSTSTORE}"
    MARATHON_SSL_KEYSTORE_PATH="${SSL_KEYSTORE_PATH}"
    MARATHON_SSL_KEYSTORE_PASSWORD="${SSL_KEYSTORE_PASSWORD}"
fi

if [ "${MESOS_FRAMEWORK_AUTHN-}" = "true" ] && [ -z "${MARATHON_DISABLE_MESOS_AUTHENTICATION+x}" ]; then
    MARATHON_MESOS_AUTHENTICATION=""
fi

$PKG_PATH/marathon/bin/marathon \
    -Djava.security.properties=/opt/mesosphere/etc/java.security \
    -Duser.dir=/var/lib/dcos/marathon \
    -J-server \
    -J-verbose:gc \
    -J-XX:+PrintGCDetails \
    -J-XX:+PrintGCTimeStamps \
    --plugin_dir "$PKG_PATH/usr/plugins/lib" \
    --plugin_conf "$PKG_PATH/usr/plugins/plugin-conf.json" \
    --master zk://zk-1.zk:2181,zk-2.zk:2181,zk-3.zk:2181,zk-4.zk:2181,zk-5.zk:2181/mesos \
    --mesos_leader_ui_url "/mesos" \
    --metrics_statsd --metrics_statsd_host "$STATSD_UDP_HOST" --metrics_statsd_port "$STATSD_UDP_PORT"
