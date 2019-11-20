#!/bin/bash
#
# SUMMARY:
#   Helper script that can fetch all logs for any cluster and outputs them in the current working directory.
#   Fetched logs are comprised of journald logs, mesos logs, sandbox logs and diagnostics bundles for all nodes.
#
# USAGE:
#   bash fetch_cluster_logs.bash open <ssh-user> <master-public-ip> [--login-token=<token>] [--identity-file=<path>] [--debug]
#   bash fetch_cluster_logs.bash enterprise <ssh-user> <master-public-ip> [--username=<username>] [--password=<password>] [--identity-file=<path>] [--debug]
#
# COMMANDS
#   open          Fetch the logs for an open cluster.
#   enterprise    Fetch the logs for an enterprise cluster.
#
# REQUIRED ARGUMENTS
#   <ssh-user>            ssh user to access the nodes of your cluster.
#   <master-public-ip>    Public ip for the master node of your cluster.
#
# OPTIONAL ARGUMENTS
#   --login-token=<token>     Token used to log in to your open DC/OS cluster. If omitted, you will be prompted for it
#                             during the DC/OS CLI cluster setup.
#   --username=<username>     Username to log in to your enterprise DC/OS cluster. If omitted, you will be prompted for
#                             it during the DC/OS CLI cluster setup.
#   --password=<password>     Password to log in to your DC/OS enterprise cluster. If omitted, you will be prompted for
#                             it during the DC/OS CLI cluster setup.
#   --identity-file=<path>    Path to the private ssh key that will be used to ssh into the nodes. If omitted, that key
#                             must be added to your ssh-agent.
#   --debug                   Turn on debug logging for the DC/OS CLI.

set +e
set -x

dcos_variant=$1
if [[ -z $dcos_variant ]] || ([[ $dcos_variant != "open" ]] && [[ $dcos_variant != "enterprise" ]]); then
  echo "ERROR: You must specify either the 'open' or 'enterprise' command depending on your cluster type."
  exit 0
fi
shift

ssh_user=$1
if [[ -z $ssh_user ]]; then
  echo "ERROR: Required argument 'ssh_user' was either not specified or null."
  exit 0
fi
shift

master_public_ip=$1
if [[ -z $master_public_ip ]]; then
  echo "ERROR: Required argument 'master_public_ip' was either not specified or null."
  exit 0
fi
shift

if [[ $dcos_variant == "open" ]]; then
  for i in "$@"
  do
  case $i in
    --debug)
      debug_options="--debug --log-level=debug"
      shift
    ;;
    --login-token=*)
      dcos_login_token_input="<<< ${i#*=}"
      shift
    ;;
      --identity-file=*)
      identity_file="${i#*=}"
    shift
    ;;
    *)
      echo "ERROR: Unrecognized argument '$i' for command '$dcos_variant'"
      exit 0
    ;;
  esac
  done
else
  for i in "$@"
  do
  case $i in
    --debug)
      debug_options="--debug --log-level=debug"
      shift
    ;;
    --username=*)
      dcos_username=$i
      shift
    ;;
    --password=*)
      dcos_password=$i
      shift
    ;;
    --identity-file=*)
      identity_file="${i#*=}"
      shift
    ;;
    *)
      echo "ERROR: Unrecognized argument '$i' for command '$dcos_variant'"
      exit 0
    ;;
  esac
  done
fi

ssh_options="-A -T -l $ssh_user -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
if [[ ! -z $identity_file ]]; then
  ssh_options="-i $identity_file ${ssh_options}"
fi

# download the DC/OS CLI
if [ ! -f dcos-cli ]; then
  wget https://downloads.dcos.io/binaries/cli/linux/x86-64/dcos-1.12/dcos --output-document=dcos-cli
  chmod +x dcos-cli
fi

# link the CLI with the cluster
if [[ $dcos_variant == "open" ]]; then
  bash -c "./dcos-cli $debug_options cluster setup $master_public_ip --insecure $dcos_login_token_input"
else
  ./dcos-cli $debug_options cluster setup $master_public_ip $dcos_username $dcos_password --insecure
fi

# generate diagnostics bundle
bundle_name=$(./dcos-cli $debug_options node diagnostics create all | grep -o bundle-.*)
echo "diagnostics bundle name: ${bundle_name}"

# wait for the diagnostics job to complete
status_output="$(./dcos-cli $debug_options node diagnostics --status)"
while [[ $status_output =~ "is_running: True" ]]; do
    echo "Diagnostics job still running. Retrying in 5 seconds."
    sleep 5
    status_output="$(./dcos-cli $debug_options node diagnostics --status)"
done

# get diagnostics bundle
./dcos-cli $debug_options node diagnostics download $bundle_name

# copy the identity file to the master node so we don't need the ssh-agent when agent forwarding
if [[ ! -z $identity_file ]]; then
  scp -i $identity_file -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null $identity_file ${ssh_user}@${master_public_ip}:~/$identity_file
fi

nodes_info_json=$(./dcos-cli $debug_options node --json)
for node_info in $(echo "$nodes_info_json" | jq -r '.[] | @base64'); do
  _jq() {
   echo "$node_info" | base64 --decode | jq -r ${1}
  }

  id=$(_jq '.id')
  pid=$(_jq '.pid')
  ip=$(_jq '.hostname')
  # converting the dots to underscores in the ip for log file names
  ip_underscores=${ip//./_}

  if [[ $pid == *"master"* ]]; then
    # get journald logs
    ssh $ssh_options $master_public_ip -- journalctl -x --no-pager > master_journald.log

    # get mesos logs
    ./dcos-cli $debug_options node log --leader > mesos_master.log
  else
    # get sandbox logs
    ssh $ssh_options $master_public_ip -- ssh $ssh_options $ip -- sudo tar --exclude=provisioner -zc /var/lib/mesos/slave > sandbox_${ip_underscores}.tar.gz

    # get journald logs
    ssh $ssh_options $master_public_ip -- ssh $ssh_options $ip -- journalctl -x --no-pager > agent_${ip_underscores}_journald.log

    # get mesos logs
    ./dcos-cli $debug_options node log --mesos-id=$id > mesos_agent_${ip_underscores}.log
  fi
done
