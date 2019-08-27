#!/bin/bash

set -exo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <test group>"
    echo "This script runs the DC/OS integration tests of the given test group against an existing cluster by using pytest-xdist."
    exit 1
fi

ssh_user=$(./terraform output --json -module dcos.dcos-infrastructure masters.os_user |jq -r '.value')
ssh_user=${ssh_user:-$(./terraform output --json -module dcos.dcos-infrastructure masters.admin_username |jq -r '.value')}
MASTER_PRIVATE_IP=$(./terraform output --json -module dcos.dcos-infrastructure masters.private_ips |jq -r '.value[0]')
MASTER_PUBLIC_IP=$(./terraform output --json -module dcos.dcos-infrastructure masters.public_ips |jq -r '.value[0]')
PUBLIC_SLAVE_HOSTS="$(./terraform output --json -module dcos.dcos-infrastructure public_agents.private_ips |jq -r '.value |join(",")')"
SLAVE_HOSTS="$(./terraform output --json -module dcos.dcos-infrastructure private_agents.private_ips |jq -r '.value |join(",")')"

if [ "$2" == "enterprise" ]; then
    # if the DC/OS variant is enterprise, we ssh into the cluster and run the tests there instead of using pytest-xdist.
    # The reason for this is open tests are ran on enterprise clusters, but these open tests live inside the cluster.
    # So in order to access them we must first ssh into the cluster. Using pytest-xdist is of no use in that scenario.
    TEST_GROUPS_PATH=/opt/mesosphere/active/dcos-integration-test/open_source_tests/get_test_group.py
    SSH="ssh  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ./id_rsa ${ssh_user}@$MASTER_PUBLIC_IP"
    LOAD_DCOS_ENVIRONMENT='source /opt/mesosphere/environment.export && cd `find /opt/mesosphere/active/ -name dcos-integration-test* | sort | tail -n 1` && '

    function run_pytest {
        $SSH -- $LOAD_DCOS_ENVIRONMENT $@
    }

    PYTEST_LOCALE=${PYTEST_LOCALE:-en_US.utf8}
    TEST_NAMES=$(run_pytest LC_ALL=$PYTEST_LOCALE LANG=$PYTEST_LOCALE python "$TEST_GROUPS_PATH" group_$1)
    run_pytest PUBLIC_SLAVE_HOSTS="$(./terraform output --json -module dcos.dcos-infrastructure public_agents.private_ips |jq -r '.value |join(",")')" \
            SLAVE_HOSTS="$(./terraform output --json -module dcos.dcos-infrastructure private_agents.private_ips |jq -r '.value |join(",")')" \
            DCOS_PROVIDER=onprem \
            DNS_SEARCH=false \
            MASTER_HOSTS="$MASTER_PRIVATE_IP" \
            DCOS_DNS_ADDRESS="http://$MASTER_PRIVATE_IP" \
            DCOS_LOGIN_UNAME=testadmin \
            DCOS_LOGIN_PW=testpassword \
            py.test ${EXTRA_PYTEST_ARGS} ${TEST_NAMES}
else
    TEST_GROUPS_PATH=/opt/mesosphere/active/dcos-integration-test/get_test_group.py
    PYTEST_LOCALE=${PYTEST_LOCALE:-en_US.utf8}
    SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ./id_rsa ${ssh_user}@$MASTER_PUBLIC_IP"
    TEST_DIR='$(find /opt/mesosphere/active/ -name dcos-integration-test* | sort | tail -n 1)'
    TEST_NAMES=$($SSH -- "LC_ALL=$PYTEST_LOCALE LANG=$PYTEST_LOCALE cd $TEST_DIR && dcos-shell python $TEST_GROUPS_PATH group_$1")

    export PUBLIC_AGENTS_PRIVATE_IPS=$PUBLIC_SLAVE_HOSTS
    export PRIVATE_AGENTS_PRIVATE_IPS=$SLAVE_HOSTS
    export MASTERS_PRIVATE_IPS=$MASTER_PRIVATE_IP
    export MASTER_PUBLIC_IP=$MASTER_PUBLIC_IP
    export DCOS_SSH_USER=$ssh_user
    export DCOS_SSH_KEY_PATH=~/.ssh/id_rsa

    cd packages/dcos-integration-test/extra
    pytest ${EXTRA_PYTEST_ARGS} ${TEST_NAMES}
fi

# if the last return code is zero, we create a file to indicate all tests passed. The existence of this
# file will be checked in the next build step to determine if log collection can be skipped.
return_code=$?
if [[ $return_code = 0 ]]; then
  touch all_tests_passed
fi
exit $return_code
