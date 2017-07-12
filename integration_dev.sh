#!/bin/bash
set -euo pipefail

TESTENV="~/testenv"

### Public API

help() {
    scriptname="$(basename $0)"

    cat <<EOF

### How to use:

    The first parameter is a function defined in this script. The rest of the
    parameters are parameters to that function.

### For example:

    export SSH_USER=core; \\
        export SSH_ADDRESS=<master_ip_here>; \\
        $scriptname setup

    export SSH_USER=core; \\
        export SSH_ADDRESS=<master_ip_here>; \\
        $scriptname push_file test_service_discovery.py test_service_discovery.py && \\
        $scriptname run_test test_service_discovery.py::test_service_discovery_mesos_overlay

EOF

    exit 1
}

setup() {
    echo "$SSH_USER" > /dev/null
    echo "$SSH_ADDRESS" > /dev/null

    publics="$(detect_public $SSH_USER $SSH_ADDRESS)"
    privates="$(detect_private $SSH_USER $SSH_ADDRESS)"

    set +e
    read -r -d '' PROFILE_VAR <<EOF
source /opt/mesosphere/packages/dcos-integration-test--*/util/test_env.export
SLAVE_HOSTS=$privates
PUBLIC_SLAVE_HOSTS=$publics
EOF
    set -e

    ssh -o "LogLevel QUIET" \
        -o "StrictHostKeyChecking no" \
        -o "UserKnownHostsFile /dev/null" \
        -A \
        "$SSH_USER@$SSH_ADDRESS" \
        "echo \"$PROFILE_VAR\" >> $TESTENV"
}

# The argument is an email address
add_user() {
    echo "$SSH_USER" > /dev/null
    echo "$SSH_ADDRESS" > /dev/null

    user="$1"

    ssh -o "LogLevel QUIET" \
        -o "StrictHostKeyChecking no" \
        -o "UserKnownHostsFile /dev/null" \
        -A \
        "$SSH_USER@$SSH_ADDRESS" \
        "source $TESTENV && dcos_add_user.py $user"
}

# Run entire suite (file): test_service_discovery.py
# Run single test: test_service_discovery.py::test_service_discovery_mesos_overlay
run_test() {
    echo "$SSH_USER" > /dev/null
    echo "$SSH_ADDRESS" > /dev/null

    teststr="$1"

    ssh -o "LogLevel QUIET" \
        -o "StrictHostKeyChecking no" \
        -o "UserKnownHostsFile /dev/null" \
        -A -t \
        "$SSH_USER@$SSH_ADDRESS" \
        "source $TESTENV && cd /opt/mesosphere/active/dcos-integration-test && py.test -s -vv $teststr"
}

# Upload a test suite file to the cluster.
#
# Arg 1: Relative path to local file
# Arg 2: Path to remote file starting from the dcos-integration-test directory
push_file() {
    echo "$SSH_USER" > /dev/null
    echo "$SSH_ADDRESS" > /dev/null

    localfile="$1"
    remotefile="$2"

    scp -o "LogLevel QUIET" \
        -o "StrictHostKeyChecking no" \
        -o "UserKnownHostsFile /dev/null" \
        "$localfile" \
        "$SSH_USER@$SSH_ADDRESS:~/tmpfile"

    ssh -o "LogLevel QUIET" \
        -o "StrictHostKeyChecking no" \
        -o "UserKnownHostsFile /dev/null" \
        -A \
        "$SSH_USER@$SSH_ADDRESS" \
        "sudo mv ~/tmpfile /opt/mesosphere/active/dcos-integration-test/$remotefile"
}

### Private functions

detect_public() {
    user=$1
    addr=$2

    ssh -o "LogLevel QUIET" \
        -o "StrictHostKeyChecking no" \
        -o "UserKnownHostsFile /dev/null" \
        -A \
        "$user@$addr" \
        "for h in \$(dig slave.mesos +short); do curl -s \$h:5051/state | grep '\"default_role\":\"slave_public\"' >/dev/null && printf \",\$h\"; done | cut -d',' -f2-"
}

detect_private() {
    user=$1
    addr=$2

    ssh -o "LogLevel QUIET" \
        -o "StrictHostKeyChecking no" \
        -o "UserKnownHostsFile /dev/null" \
        -A \
        "$user@$addr" \
        "for h in \$(dig slave.mesos +short); do curl -s \$h:5051/state | grep '\"default_role\":\"slave_public\"' >/dev/null || printf \",\$h\"; done | cut -d',' -f2-"
}

### main

[ $# -eq 0 ] && help
type "$1" 2>&1 >/dev/null || help

"$1" "${@:2}"
