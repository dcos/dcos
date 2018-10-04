#!/bin/bash
#
# SUMMARY:
# Helper script that can fetch all logs for any cluster and outputs them in the current working directory.
# Fetched logs are comprised of journald logs, mesos sandbox logs and diagnostics bundles for all nodes.
#
# USAGE:
# ./fetch_cluster_logs <master_public_ip> <ssh_user> --dcos_login_token=<dcos_login_token> --identity_file=<identity_file>

set +e
set -x

master_public_ip=$1
if [[ -z $master_public_ip ]]; then
  echo "ERROR: Required argument 'master_public_ip' was either not specified or null."
  exit 0
fi

ssh_user=$2
if [[ -z $ssh_user ]]; then
  echo "ERROR: Required argument 'ssh_user' was either not specified or null."
  exit 0
fi

for i in "$@"
do
case $i in
    --dcos_login_token=*)
    dcos_login_token="${i#*=}"
    shift
    ;;
    --identity_file=*)
    identity_file="${i#*=}"
    shift
    ;;
esac
done

ssh_options="-o StrictHostKeyChecking=no"
if [[ ! -z $identity_file ]]; then
  ssh_options="${ssh_options} -o IdentityFile=$identity_file"
fi

# download the dcos-cli and link it with the cluster
if [ ! -f dcos-cli ]; then
  wget https://downloads.dcos.io/binaries/cli/linux/x86-64/dcos-1.12/dcos --output-document=dcos-cli
  chmod +x dcos-cli
fi
if [[ -z $dcos_login_token ]]; then
  # This will open a web browser and prompt the user for the login token
  ./dcos-cli --debug --log-level=debug cluster setup $master_public_ip --insecure
else
  ./dcos-cli --debug --log-level=debug cluster setup $master_public_ip --insecure <<< $dcos_login_token
fi

# generate diagnostics bundle
bundle_name=$(./dcos-cli node diagnostics create all | grep -o bundle-.*)
echo "diagnostics bundle name: ${bundle_name}"

# wait for the diagnostics job to complete
status_output="$(./dcos-cli node diagnostics --status)"
while [[ $status_output =~ "is_running: True" ]]; do
    echo "Diagnostics job still running. Retrying in 5 seconds."
    sleep 5
    status_output="$(./dcos-cli node diagnostics --status)"
done

# get diagnostics bundle
./dcos-cli node diagnostics download $bundle_name

# copy the identity file to the master node to avoid using the ssh-agent when agent forwarding
if [[ ! -z $identity_file ]]; then
  scp $ssh_options $identity_file ${ssh_user}@${master_public_ip}:~/$identity_file
fi

nodes_info_json=$(./dcos-cli node --json)
for node_info in $(echo "$nodes_info_json" | jq -r '.[] | @base64'); do
  _jq() {
   echo "$node_info" | base64 --decode | jq -r ${1}
  }

  id=$(_jq '.id')
  pid=$(_jq '.pid')
  ip=$(_jq '.hostname')

  if [[ $pid == *"master"* ]]; then
    # get journald logs
    ssh -A -t $ssh_options -l $ssh_user $master_public_ip -- journalctl -x -b > ${pid}_journald.log

    # get mesos sandbox logs
    ./dcos-cli node log --leader > ${pid}_sandbox.log
  else
    # get journald logs
    ssh -A -t $ssh_options -l $ssh_user $master_public_ip -- ssh -A -t $ssh_options -l $ssh_user $ip -- '"journalctl -x -b > logs && cat logs"' > ${pid}_journald.log

    # get mesos sandbox logs
    ./dcos-cli node log --mesos-id=$id > ${pid}_sandbox.log
  fi
done

