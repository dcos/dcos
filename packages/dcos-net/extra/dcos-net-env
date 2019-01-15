#!/bin/bash

set -e

APP_NAME=dcos-net
NODE_NAME=navstar

# Export
for ENV_FILE in \
        "/opt/mesosphere/environment" \
        "/opt/mesosphere/etc/dcos_net" \
        "/opt/mesosphere/etc/dns_config" ; \
    do
    source "${ENV_FILE}"
done

for ENV_FILE in \
        "/opt/mesosphere/etc/dns_config_master" \
        "/run/dcos/etc/${APP_NAME}_auth.env"; \
    do
    if [ -f "${ENV_FILE}" ]; then
        source "${ENV_FILE}"
    fi
done

### Usage
USAGE=""
KNOWNCMD=false
for cmd in 'console' 'foreground' 'console_clean' 'console_boot' \
           'pid' 'ping' 'remote_console' 'rpc' 'rpcterms' 'eval' 'status'; do
    USAGE="${USAGE}|${cmd}"
    [ "$1" == "${cmd}" ] && KNOWNCMD=true || true
done
if [ "${KNOWNCMD}" == "false" ]; then
    printf "Usage: %s {%s}\n" "$0" "${USAGE:1}" >&2
    exit 1
fi

### Functions

function detect_ip() {
    IP=$(/opt/mesosphere/bin/detect_ip)
    IPFILE="/var/lib/dcos/${NODE_NAME}/ip"
    read -r -d '' EVALCODE <<- EOM
        case inet:parse_ipv4strict_address("$(printf '%q' ${IP})") of
            {ok, _} -> halt(1);
            {error, _} -> halt(0)
        end.
EOM
    if /opt/mesosphere/bin/erl -noinput -eval "${EVALCODE}"; then
        echo "Bad detect_ip: ${IP}" >&2
        exit 1
    fi
    if [ -f "${IPFILE}" ]; then
        OLD_IP=$(cat ${IPFILE})
        if [ "${OLD_IP}" != "${IP}" ]; then
            echo "ERROR: IP address was changed ${OLD_IP} -> ${IP}" >&2
            echo "Please check new IP address and remove /var/lib/dcos/${NODE_NAME} directory" >&2
            exit 1
        fi
    else
        echo -n "${IP}" > "${IPFILE}"
    fi
    echo "${IP}"
}

function cookie() {
    FILE="/var/lib/dcos/cluster-id"
    if [ "${DCOS_NET_CLUSTER_IDENTITY}" == "false" ]; then
        echo 'minuteman'
    elif [ ! -f ${FILE} ]; then
        echo "ERROR: required file ${FILE} does not exists" >&2
        exit 1
    else
        cat ${FILE}
    fi
}

APP_DIR="/opt/mesosphere/active/${APP_NAME}/${APP_NAME}"

### dcos-net ebin directory
if [ -z "${DCOS_NET_EBIN}" ]; then
    DCOS_NET_APP="dcos_net.app"
    DCOS_NET_EBIN=$(find "${APP_DIR}/lib" -name "${DCOS_NET_APP}" -printf "%h")
fi
if [ -z "${DCOS_NET_EBIN}" ]; then
    echo "ebin directory was not found" >&2
    exit 1
fi
ERL_FLAGS="${ERL_FLAGS} -pa ${DCOS_NET_EBIN}"

### EPMD
EPMD_MODULE="dcos_net_epmd"
ERL_FLAGS="${ERL_FLAGS} -epmd_module ${EPMD_MODULE}"
ERL_FLAGS="${ERL_FLAGS} -start_epmd false -no_epmd"

### SSL / Distributed Erlang config
ERL_FLAGS="${ERL_FLAGS} -proto_dist dcos_net"
TLS_CONFIG="/opt/mesosphere/etc/dcos-net.config.d/tls.config"
if [ -f "${TLS_CONFIG}" ]; then
    ERL_FLAGS="${ERL_FLAGS} -ssl_dist_optfile ${TLS_CONFIG}"
fi

### Export Auth Token
export SERVICE_AUTH_TOKEN

### Export Erlang configuration
export ERL_FLAGS

### Export relx configuration
export RELX_REPLACE_OS_VARS=true
export RELX_OUT_FILE_PATH="/tmp"

### Export dns configuration
export MASTER_SOURCE
export EXHIBITOR_URI
export EXHIBITOR_ADDRESS

### Node configuration
IP=$(detect_ip)
export NAME="${NODE_NAME}@${IP}"
export COOKIE=$(cookie)

### Set application name
export ESCRIPT_NAME="${APP_DIR}"

### Set script
if [ -z "${DCOS_NET_ENV_CMD}" ]; then
    DCOS_NET_ENV_CMD="${APP_DIR}/bin/${APP_NAME}"
fi

exec "${DCOS_NET_ENV_CMD}" "$@" || exit 1
