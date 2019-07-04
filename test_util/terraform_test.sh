#!/bin/bash

if [ $# -lt 1 ]; then
    echo "Usage: $0 <test group>"
    echo "This script runs the DC/OS integration tests against an existing cluster, by SSHing into the master node and running the tests."
    exit 1
fi

set +e
set -x
set -o pipefail

MASTER_IP=$(./terraform output --json masters-ips |jq -r '.value[0]')
ssh_user=$(./terraform output --json -module dcos.dcos-infrastructure masters.os_user |jq -r '.value')
ssh_user=${ssh_user:-$(./terraform output --json -module dcos.dcos-infrastructure masters.admin_username |jq -r '.value')}

SSH="ssh  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ./id_rsa ${ssh_user}@$MASTER_IP"
LOAD_DCOS_ENVIRONMENT='source /opt/mesosphere/environment.export && cd `find /opt/mesosphere/active/ -name dcos-integration-test* | sort | tail -n 1` && '

function run_pytest {
     $SSH -- $LOAD_DCOS_ENVIRONMENT $@
}

PUBLIC_MASTER_HOSTS=$(./terraform output --json -module dcos.dcos-infrastructure masters.private_ips |jq -r '.value[0]')

TEST_GROUPS_PATH=/opt/mesosphere/active/dcos-integration-test/get_test_group.py
if [ "$2" == "enterprise" ]; then
    TEST_GROUPS_PATH=/opt/mesosphere/active/dcos-integration-test/open_source_tests/get_test_group.py
fi

PYTEST_LOCALE=${PYTEST_LOCALE:-en_US.utf8}

TEST_NAMES=$(run_pytest LC_ALL=$PYTEST_LOCALE LANG=$PYTEST_LOCALE python "$TEST_GROUPS_PATH" group_$1)
run_pytest PUBLIC_SLAVE_HOSTS="$(./terraform output --json -module dcos.dcos-infrastructure public_agents.private_ips |jq -r '.value |join(",")')" \
           SLAVE_HOSTS="$(./terraform output --json -module dcos.dcos-infrastructure private_agents.private_ips |jq -r '.value |join(",")')" \
           DCOS_PROVIDER=onprem \
           DNS_SEARCH=false \
           DCOS_CLI_URL="https://downloads.dcos.io/binaries/cli/linux/x86-64/dcos-1.12/dcos" \
           PUBLIC_MASTER_HOSTS="$PUBLIC_MASTER_HOSTS" \
           MASTER_HOSTS="$PUBLIC_MASTER_HOSTS" \
           DCOS_DNS_ADDRESS="http://$PUBLIC_MASTER_HOSTS" \
           DCOS_LOGIN_UNAME=testadmin \
           DCOS_LOGIN_PW=testpassword \
           py.test ${EXTRA_PYTEST_ARGS} ${TEST_NAMES}

# if the last return code is zero, we create a file to indicate all tests passed. The existence of this
# file will be checked in the next build step to determine if log collection can be skipped.
return_code=$?
if [[ $return_code = 0 ]]; then
  touch all_tests_passed
fi
exit $return_code
