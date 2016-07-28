#!/bin/bash
# Will continually poll the cluster until the desired number of masters and
# agents is reached. Override testing dir and cmd with DCOS_PYTEST_*

while true; do
    agent_count=`dig slave.mesos +short | wc -l`
    master_count=`dig master.mesos +short | wc -l`
    if [ "$agent_count" -eq "$DCOS_NUM_AGENTS" ] && [ "$master_count" -eq "$DCOS_NUM_MASTERS" ]; then
        echo 'All expected nodes have registered!'
        break
    fi
    sleep 1
done
source test_env.export
pushd ${DCOS_PYTEST_DIR:='/opt/mesosphere/active/dcos-integration-test'}
eval ${DCOS_PYTEST_CMD:='py.test -vv'}
popd
