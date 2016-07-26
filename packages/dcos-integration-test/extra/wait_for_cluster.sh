#!/bin/bash
# Will continually poll the cluster until the desired number of masters and agents is reached

while true; do
    agent_count=`dig slave.mesos +short | wc -l`
    master_count=`dig slave.mesos +short | wc -l`
    if [ "$agent_list" -eq "$DCOS_NUM_AGENTS" ] && [ "$master_count" -eq "$DCOS_NUM_MASTERS" ]; then
        echo 'All expected nodes have registered!'
        break
    fi
    sleep 1
done
