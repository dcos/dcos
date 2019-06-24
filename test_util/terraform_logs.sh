#!/bin/bash

set -x
set +e

master_ip=$(./terraform output --json masters-ips |jq -r '.value[0]')
master_fqdn=$(./terraform output --json cluster-address |jq -r '.value')
ssh_user=$(./terraform output --json -module dcos.dcos-infrastructure masters.os_user |jq -r '.value')

ssh -i id_rsa -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ${ssh_user}@$master_ip -- "ls pytest_output || exit 0; cat pytest_output | tail -n 10 | grep -q xfailed"
if [[ ( $? != 0 ) && ( -f all_tests_passed ) ]]; then
  exit 0
fi

rm -rf logs/
mkdir logs/
cd logs/

wget https://raw.githubusercontent.com/dcos/dcos/master/fetch_cluster_logs.bash

if [ "$1" == "enterprise" ]; then
    bash fetch_cluster_logs.bash enterprise "$ssh_user" "$master_fqdn" --username=testadmin --password=testpassword --identity-file=../id_rsa --max-artifact-size=${MAX_ARTIFACT_SIZE_MB:-1000} --debug
else
    extra_args=""
    if [ "$DCOS_OPEN_LOGIN_TOKEN" != "" ]; then
        extra_args="--login-token=$DCOS_OPEN_LOGIN_TOKEN"
    fi

    bash fetch_cluster_logs.bash open "$ssh_user" "$master_fqdn" --identity-file=../id_rsa --max-artifact-size=${MAX_ARTIFACT_SIZE_MB:-1000} --debug $extra_args
fi
