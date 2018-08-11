import asyncio
import json
import logging
import os
from typing import Optional

import pkgpanda
import ssh.utils
from dcos_installer.constants import (
    BOOTSTRAP_DIR,
    CHECK_RUNNER_CMD,
    CLUSTER_PACKAGES_PATH,
    PACKAGE_LIST_DIR,
    SERVE_DIR,
    SSH_KEY_PATH,
)
from pkgpanda.constants import is_windows
from ssh.runner import Node


REMOTE_TEMP_DIR = os.sep + 'opt' + os.sep + 'dcos_install_tmp'

if is_windows:
    script_extension = "ps1"
else:
    script_extension = "sh"

log = logging.getLogger(__name__)


def get_async_runner(config, hosts, async_delegate=None):
    # TODO(cmaloney): Delete these repeats. Use gen / expanded configuration to get all the values.
    process_timeout = config.hacky_default_get('process_timeout', 120)
    extra_ssh_options = config.hacky_default_get('extra_ssh_options', '')
    ssh_key_path = config.hacky_default_get('ssh_key_path', SSH_KEY_PATH)

    # if ssh_parallelism is not set, use 20 concurrent ssh sessions by default.
    parallelism = config.hacky_default_get('ssh_parallelism', 20)

    return ssh.runner.MultiRunner(
        hosts,
        user=config['ssh_user'],
        key_path=ssh_key_path,
        process_timeout=process_timeout,
        extra_opts=extra_ssh_options,
        async_delegate=async_delegate,
        parallelism=parallelism,
        default_port=int(config.hacky_default_get('ssh_port', 22)))


def add_pre_action(chain, ssh_user):
    # Do setup steps for a chain
    if is_windows:
        chain.add_execute(['cmd.exe', '/c', 'mkdir', REMOTE_TEMP_DIR], stage='Creating temp directory')
    else:
        chain.add_execute(['sudo', 'mkdir', '-p', REMOTE_TEMP_DIR], stage='Creating temp directory')
        chain.add_execute(['sudo', 'chown', ssh_user, REMOTE_TEMP_DIR],
                          stage='Ensuring {} owns temporary directory'.format(ssh_user))


def add_post_action(chain):
    # Do cleanup steps for a chain
    if is_windows:
        chain.add_execute(['cmd.exe', '/c', 'rmdir', '/s', '/q', REMOTE_TEMP_DIR],
                          stage='Cleaning up temporary directory')
    else:
        chain.add_execute(['sudo', 'rm', '-rf', REMOTE_TEMP_DIR],
                          stage='Cleaning up temporary directory')


class ExecuteException(Exception):
    """Raised when execution fails"""


def nodes_count_by_type(config):
    total_agents_count = len(config.hacky_default_get('agent_list', [])) + \
        len(config.hacky_default_get('public_agent_list', []))
    return {
        'total_masters': len(config['master_list']),
        'total_agents': total_agents_count
    }


def get_full_nodes_list(config):
    def add_nodes(nodes, tag):
        return [Node(node, tag, default_port=int(config.hacky_default_get('ssh_port', 22)))
                for node in nodes]

    node_role_map = {
        'master_list': 'master',
        'agent_list': 'agent',
        'public_agent_list': 'public_agent'
    }
    full_target_list = []
    for config_field, role in node_role_map.items():
        if config_field in config:
            full_target_list += add_nodes(config[config_field], {'role': role})
    log.debug("full_target_list: {}".format(full_target_list))
    return full_target_list


@asyncio.coroutine
def run_preflight(config, pf_script_path=(SERVE_DIR + os.sep + 'dcos_install.' + script_extension), block=False,
                  state_json_dir=None, async_delegate=None, retry=False, options=None):
    '''
    Copies preflight.sh to target hosts and executes the script. Gathers
    stdout, sterr and return codes and logs them to disk via SSH library.
    :param config: Dict, loaded config file from genconf/config.yaml
    :param pf_script_path: preflight.sh script location on a local host
    :param preflight_remote_path: destination location
    '''
    if not os.path.isfile(pf_script_path):
        log.error("{} does not exist. Please run --genconf before executing preflight.".format(pf_script_path))
        raise FileNotFoundError('{} does not exist'.format(pf_script_path))
    targets = get_full_nodes_list(config)

    pf = get_async_runner(config, targets, async_delegate=async_delegate)
    chains = []

    preflight_chain = ssh.utils.CommandChain('preflight')

    add_pre_action(preflight_chain, pf.user)
    preflight_chain.add_copy(pf_script_path, REMOTE_TEMP_DIR, stage='Copying preflight script')

    if is_windows:
        preflight_chain.add_execute(
            'powershell.exe -file  {} --preflight-only master'.format(
                os.path.join(REMOTE_TEMP_DIR, os.path.basename(pf_script_path))).split(),
            stage='Executing preflight check')
    else:
        preflight_chain.add_execute(
            'sudo bash {} --preflight-only master'.format(
                os.path.join(REMOTE_TEMP_DIR, os.path.basename(pf_script_path))).split(),
            stage='Executing preflight check')
    chains.append(preflight_chain)

    # Setup the cleanup chain
    cleanup_chain = ssh.utils.CommandChain('preflight_cleanup')
    add_post_action(cleanup_chain)
    chains.append(cleanup_chain)
    result = yield from pf.run_commands_chain_async(chains, block=block, state_json_dir=state_json_dir,
                                                    delegate_extra_params=nodes_count_by_type(config))
    return result


def _add_copy_dcos_install(chain, local_install_path=SERVE_DIR):
    dcos_install_script = 'dcos_install.' + script_extension
    local_install_path = os.path.join(local_install_path, dcos_install_script)
    remote_install_path = os.path.join(REMOTE_TEMP_DIR, dcos_install_script)
    chain.add_copy(local_install_path, remote_install_path, stage='Copying dcos_install.' + script_extension)


def _add_copy_package_list(chain, local_package_list_path):
    remote_dir = os.path.join(REMOTE_TEMP_DIR, 'package_lists')
    if is_windows:
        chain.add_execute(['cmd.exe', '/c', 'mkdir', remote_dir], stage='Creating directory')
    else:
        chain.add_execute(['mkdir', '-p', remote_dir], stage='Creating directory')
    chain.add_copy(local_package_list_path, remote_dir, stage='Copying package list')


def _add_copy_packages(chain, local_pkg_base_path=SERVE_DIR):
    if not os.path.isfile(CLUSTER_PACKAGES_PATH):
        err_msg = '{} not found'.format(CLUSTER_PACKAGES_PATH)
        log.error(err_msg)
        raise ExecuteException(err_msg)

    cluster_packages = pkgpanda.load_json(CLUSTER_PACKAGES_PATH)
    for package, params in cluster_packages.items():
        destination_package_dir = os.path.join(REMOTE_TEMP_DIR, 'packages', package)
        local_pkg_path = os.path.join(local_pkg_base_path, params['filename'])

        if is_windows:
            chain.add_execute(['cmd.exe', '/c', 'mkdir', destination_package_dir], stage='Creating package directory')
        else:
            chain.add_execute(['mkdir', '-p', destination_package_dir], stage='Creating package directory')
        chain.add_copy(local_pkg_path, destination_package_dir,
                       stage='Copying packages')


def _add_copy_bootstap(chain, local_bs_path):
    remote_bs_path = REMOTE_TEMP_DIR + '/bootstrap'
    if is_windows:
        chain.add_execute(['cmd.exe', '/c', 'mkdir', remote_bs_path], stage='Creating directory')
    else:
        chain.add_execute(['mkdir', '-p', remote_bs_path], stage='Creating directory')
    chain.add_copy(local_bs_path, remote_bs_path,
                   stage='Copying bootstrap')


def _get_bootstrap_tarball(tarball_base_dir=BOOTSTRAP_DIR):
    '''
    Get a bootstrap tarball from a local filesystem
    :return: String, location of a tarball
    '''
    if 'BOOTSTRAP_ID' not in os.environ:
        err_msg = 'BOOTSTRAP_ID must be set'
        log.error(err_msg)
        raise ExecuteException(err_msg)

    tarball = os.path.join(tarball_base_dir, '{}.bootstrap.tar.xz'.format(os.environ['BOOTSTRAP_ID']))
    if not os.path.isfile(tarball):
        log.error('Ensure environment variable BOOTSTRAP_ID is set correctly')
        log.error('Ensure that the bootstrap tarball exists in '
                  '{}/[BOOTSTRAP_ID].bootstrap.tar.xz'.format(tarball_base_dir))
        log.error('You must run genconf.py before attempting Deploy.')
        raise ExecuteException('bootstrap tarball not found in {}'.format(tarball_base_dir))
    return tarball


def _get_cluster_package_list(serve_dir: str=SERVE_DIR, package_list_base_dir: str=PACKAGE_LIST_DIR) -> str:
    """Return the local filename for the cluster package list."""
    latest_filename = os.path.join(SERVE_DIR, 'cluster-package-list.latest')
    if not os.path.exists(latest_filename):
        err_msg = 'Unable to find {}'.format(latest_filename)
        log.error(err_msg)
        log.error('You must run genconf.py before attempting Deploy.')
        raise ExecuteException(err_msg)

    with open(latest_filename) as f:
        latest_id = f.read().strip()

    package_list_filename = os.path.join(package_list_base_dir, '{}.package_list.json'.format(latest_id))
    if not os.path.exists(package_list_filename):
        err_msg = 'Unable to find {}'.format(package_list_filename)
        log.error(err_msg)
        log.error('You must run genconf.py before attempting Deploy.')
        raise ExecuteException(err_msg)

    return package_list_filename


def _read_state_file(state_file):
    if not os.path.isfile(state_file):
        return {}

    with open(state_file) as fh:
        return json.load(fh)


def _remove_host(state_file, host):

    json_state = _read_state_file(state_file)

    if 'hosts' not in json_state or host not in json_state['hosts']:
        return False

    log.debug('removing host {} from {}'.format(host, state_file))
    try:
        del json_state['hosts'][host]
    except KeyError:
        return False

    with open(state_file, 'w') as fh:
        json.dump(json_state, fh)

    return True


@asyncio.coroutine
def install_dcos(
        config,
        block=False,
        state_json_dir=None,
        hosts: Optional[list]=None,
        async_delegate=None,
        try_remove_stale_dcos=False,
        **kwargs):
    if hosts is None:
        hosts = []

    # Role specific parameters
    role_params = {
        'agent': {
            'tags': {'role': 'agent', 'dcos_install_param': 'slave'},
            'hosts': config.hacky_default_get('agent_list', [])
        },
        'public_agent': {
            'tags': {'role': 'public_agent', 'dcos_install_param': 'slave_public'},
            'hosts': config.hacky_default_get('public_agent_list', [])
        }
    }
    if not is_windows:
        role_params += {
            'master': {
                'tags': {'role': 'master', 'dcos_install_param': 'master'},
                'hosts': config['master_list']
            }
        }

    bootstrap_tarball = _get_bootstrap_tarball()
    log.debug("Local bootstrap found: %s", bootstrap_tarball)
    cluster_package_list = _get_cluster_package_list()
    log.debug("Local cluster package list found: %s", cluster_package_list)

    targets = []
    if hosts:
        targets = hosts
    else:
        for role, params in role_params.items():
            targets += [Node(node, params['tags'], default_port=int(config.hacky_default_get('ssh_port', 22)))
                        for node in params['hosts']]

    runner = get_async_runner(config, targets, async_delegate=async_delegate)
    chains = []
    if try_remove_stale_dcos:
        pkgpanda_uninstall_chain = ssh.utils.CommandChain('remove_stale_dcos')
        if is_windows:
            pkgpanda_uninstall_chain.add_execute(['c:\\opt\\mesosphere\\bin\\scripts\\pkgpanda.exe', 'uninstall'],
                                                 stage='Trying pkgpanda uninstall')
        else:
            pkgpanda_uninstall_chain.add_execute(['sudo', '-i', '/opt/mesosphere/bin/pkgpanda', 'uninstall'],
                                                 stage='Trying pkgpanda uninstall')
        chains.append(pkgpanda_uninstall_chain)

        remove_dcos_chain = ssh.utils.CommandChain('remove_stale_dcos')
        if is_windows:
            remove_dcos_chain.add_execute(['cmd.exe', '/c', 'rmdir', '/q', '/s', 'c:\\opt\\mesosphere'],
                                          stage="Removing DC/OS files")
            remove_dcos_chain.add_execute(['cmd.exe', '/c', 'rmdir', '/q', '/s', 'c:\\etc\\mesosphere'],
                                          stage="Removing DC/OS files")
        else:
            remove_dcos_chain.add_execute(['rm', '-rf', '/opt/mesosphere', '/etc/mesosphere'],
                                          stage="Removing DC/OS files")
        chains.append(remove_dcos_chain)

    chain = ssh.utils.CommandChain('deploy')
    chains.append(chain)

    add_pre_action(chain, runner.user)
    _add_copy_dcos_install(chain)
    _add_copy_packages(chain)
    _add_copy_bootstap(chain, bootstrap_tarball)
    _add_copy_package_list(chain, cluster_package_list)

    if is_windows:
        chain.add_execute(
            lambda node: (
                'powershell.exe -file {}\\dcos_install.ps1 {}'.
                format(REMOTE_TEMP_DIR, node.tags['dcos_install_param'])).split(),
            stage=lambda node: 'Installing DC/OS'
        )
    else:
        chain.add_execute(
            lambda node: (
                'sudo bash {}/dcos_install.sh {}'.format(REMOTE_TEMP_DIR, node.tags['dcos_install_param'])).split(),
            stage=lambda node: 'Installing DC/OS'
        )

    # UI expects total_masters, total_agents to be top level keys in deploy.json
    delegate_extra_params = nodes_count_by_type(config)
    if kwargs.get('retry') and state_json_dir:
        state_file_path = os.path.join(state_json_dir, 'deploy.json')
        log.debug('retry executed for a state file deploy.json')
        for _host in hosts:
            _remove_host(state_file_path, '{}:{}'.format(_host.ip, _host.port))

        # We also need to update total number of hosts
        json_state = _read_state_file(state_file_path)
        delegate_extra_params['total_hosts'] = json_state['total_hosts']

    # Setup the cleanup chain
    cleanup_chain = ssh.utils.CommandChain('deploy_cleanup')
    add_post_action(cleanup_chain)
    chains.append(cleanup_chain)

    result = yield from runner.run_commands_chain_async(chains, block=block, state_json_dir=state_json_dir,
                                                        delegate_extra_params=delegate_extra_params)
    return result


@asyncio.coroutine
def run_postflight(config, block=False, state_json_dir=None, async_delegate=None, retry=False, options=None):
    targets = get_full_nodes_list(config)
    node_runner = get_async_runner(config, targets, async_delegate=async_delegate)
    cluster_runner = get_async_runner(config, [targets[0]], async_delegate=async_delegate)

    # Run the check script for up to 15 minutes (900 seconds) to ensure we do not return failure on a cluster
    # that is still booting.
    check_script_template = """
T=900
until OUT=$(sudo /opt/mesosphere/bin/dcos-shell {check_cmd} {check_type}) || [[ T -eq 0 ]]; do
    sleep 1
    let T=T-1
done
RETCODE=$?
echo $OUT
exit $RETCODE"""
    node_check_script = check_script_template.format(
        check_cmd=CHECK_RUNNER_CMD,
        check_type='node-poststart')
    cluster_check_script = check_script_template.format(
        check_cmd=CHECK_RUNNER_CMD,
        check_type='cluster')

    node_postflight_chain = ssh.utils.CommandChain('postflight')
    node_postflight_chain.add_execute(
        [node_check_script],
        stage='Executing node postflight checks')

    cluster_postflight_chain = ssh.utils.CommandChain('cluster_postflight')
    cluster_postflight_chain.add_execute(
        [cluster_check_script],
        stage='Executing cluster postflight checks')

    node_check_result = yield from node_runner.run_commands_chain_async(
        [node_postflight_chain],
        block=block,
        state_json_dir=state_json_dir,
        delegate_extra_params=nodes_count_by_type(config))

    cluster_check_result = yield from cluster_runner.run_commands_chain_async(
        [cluster_postflight_chain],
        block=block,
        state_json_dir=state_json_dir)

    if block:
        result = node_check_result + cluster_check_result
    else:
        result = None
    return result


# TODO: DCOS-250 (skumaran@mesosphere.com)- Create an comprehensive DC/OS uninstall strategy.
# This routine is currently unused and unexposed.
@asyncio.coroutine
def uninstall_dcos(config, block=False, state_json_dir=None, async_delegate=None, options=None):
    targets = get_full_nodes_list(config)

    # clean the file to all targets
    runner = get_async_runner(config, targets, async_delegate=async_delegate)
    uninstall_chain = ssh.utils.CommandChain('uninstall')

    if is_windows:
        uninstall_chain.add_execute([
            'c:\\opt\\mesosphere\\bin\\scripts\\pkgpanda',
            'uninstall',
            '&&',
            'cmd.exe',
            '/c',
            'rmdir',
            '/s',
            '/q',
            'c:\\opt\\mesosphere\\'], stage='Uninstalling DC/OS')
    else:
        uninstall_chain.add_execute([
            'sudo',
            '-i',
            '/opt/mesosphere/bin/pkgpanda',
            'uninstall',
            '&&',
            'sudo',
            'rm',
            '-rf',
            '/opt/mesosphere/'], stage='Uninstalling DC/OS')
    result = yield from runner.run_commands_chain_async([uninstall_chain], block=block, state_json_dir=state_json_dir)

    return result


def _add_prereqs_script(chain):

    if is_windows:
        inline_script = r"""
write-output "No prereqisits needed at this time"
"""
    else:
        inline_script = r"""
#!/usr/bin/env bash

# Exit on error, unset variable, or error in pipe chain
set -o errexit -o nounset -o pipefail

# For xfs_info
PATH=$PATH:/usr/sbin:/sbin

echo "Validating distro..."
distro="$(source /etc/os-release && echo "${ID}")"
if [[ "${distro}" == 'coreos' ]]; then
  echo "Distro: CoreOS"
  echo "All prerequisites already installed"
  exit 0
elif [[ "${distro}" == 'rhel' ]]; then
  echo "Distro: RHEL"
elif [[ "${distro}" == 'centos' ]]; then
  echo "Distro: CentOS"
else
  echo "Distro: ${distro}"
  echo "Error: Distro ${distro} is not supported. Only CoreOS, RHEL, and CentOS are supported." >&2
  exit 1
fi

echo "Validating distro version..."
# CentOS & RHEL < 7 have inconsistent release file locations
distro_major_version="$(source /etc/os-release && echo "${VERSION_ID}" | sed -e 's/^\([0-9][0-9]*\).*$/\1/')"
if [[ ${distro_major_version} -lt 7 ]]; then
  echo "Error: Distro version ${distro_major_version} is not supported. Only >= 7 is supported." >&2
  exit 1
fi
# CentOS & RHEL >= 7 both have the full version in /etc/redhat-release
distro_minor_version="$(cat /etc/redhat-release | sed -e 's/[^0-9]*[0-9][0-9]*\.\([0-9][0-9]*\).*/\1/')"
echo "Distro Version: ${distro_major_version}.${distro_minor_version}"
if [[ ${distro_major_version} -eq 7 && ${distro_minor_version} -lt 2 ]]; then
  echo "Error: Distro version ${distro_major_version}.${distro_minor_version} is not supported. "\
"Only >= 7.2 is supported." >&2
  exit 1
fi

echo "Validating kernel version..."
kernel_major_version="$(uname -r | sed -e 's/\([0-9][0-9]*\).*/\1/')"
kernel_minor_version="$(uname -r | sed -e "s/${kernel_major_version}\.\([0-9][0-9]*\).*/\1/")"
echo "Kernel Version: ${kernel_major_version}.${kernel_minor_version}"
if [[ ${kernel_major_version} -lt 3 ]] ||
   [[ ${kernel_major_version} -eq 3 && ${kernel_minor_version} -lt 10 ]]; then
  echo -n "Error: Kernel version ${kernel_major_version}.${kernel_minor_version} is not supported. " >&2
  echo "Only >= 3.10 is supported." >&2
  exit 1
fi

echo "Validating kernel modules..."
if ! lsmod | grep -q overlay; then
  echo "Enabling OverlayFS kernel module..."
  # Enable now
  sudo modprobe overlay
  # Load on reboot via systemd
  sudo tee /etc/modules-load.d/overlay.conf <<-'EOF'
overlay
EOF
fi

echo "Detecting Docker..."
if hash docker 2>/dev/null; then
  docker_client_version="$(docker --version | sed -e 's/Docker version \(.*\),.*/\1/')"
  echo "Docker Client Version: ${docker_client_version}"

  if ! sudo docker info &>/dev/null; then
    echo "Docker Server not found. Please uninstall Docker and try again." >&2
    exit 1
  fi

  docker_server_version="$(sudo docker info | grep 'Server Version:' | sed -e 's/Server Version: \(.*\)/\1/')"
  echo "Docker Server Version: ${docker_server_version}"

  if [[ "${docker_client_version}" != "${docker_server_version}" ]]; then
    echo "Docker Server and Client versions do not match. Please uninstall Docker and try again." >&2
    exit 1
  fi

  # Require Docker >= 1.11
  docker_major_version="$(echo "${docker_server_version}" | sed -e 's/\([0-9][0-9]*\)\.\([0-9][0-9]*\).*/\1/')"
  docker_minor_version="$(echo "${docker_server_version}" | sed -e 's/\([0-9][0-9]*\)\.\([0-9][0-9]*\).*/\2/')"
  if [[ ${docker_major_version} -lt 1 ]] ||
     [[ ${docker_major_version} -eq 1 && ${docker_minor_version} -lt 11 ]]; then
    echo -n "Docker version ${docker_major_version}.${docker_minor_version} not supported. " >&2
    echo "Please uninstall Docker and try again." >&2
    exit 1
  fi

  install_docker='false'
else
  echo "Docker not found (install queued)"
  install_docker='true'
fi

echo "Validating Docker Data Root..."
if [[ "${install_docker}" == 'true' ]]; then
  docker_data_root="/var/lib/docker"
else
  docker_data_root="$(sudo docker info | grep 'Docker Root Dir:' | sed -e 's/Docker Root Dir: \(.*\)/\1/')"
fi
echo "Docker Data Root: ${docker_data_root}"
sudo mkdir -p "${docker_data_root}"

file_system="$(sudo df --output=fstype "${docker_data_root}" | tail -1)"
echo "File System: ${file_system}"
if [[ "${file_system}" != 'xfs' ]] || ! sudo xfs_info "${docker_data_root}" | grep -q 'ftype=1'; then
  echo "Error: "${docker_data_root}" must use XFS provisioned with ftype=1 to avoid known issues with OverlayFS." >&2
  exit 1
fi

function yum_install() {
  local cmd="$1"
  echo "Validating ${cmd}..."
  if ! hash "${cmd}" 2>/dev/null; then
    echo "Installing ${cmd}..."
    sudo yum install -y ${cmd}
  fi
  # print installed version
  rpm -q "${cmd}"
}

echo "Installing Utilities..."
yum_install wget
yum_install curl
yum_install git
yum_install unzip
yum_install xz
yum_install ipset

if [[ "${install_docker}" == 'true' ]]; then
  echo "Installing Docker..."

  # Add Docker Yum Repo
  sudo tee /etc/yum.repos.d/docker.repo <<-'EOF'
[dockerrepo]
name=Docker Repository
baseurl=https://yum.dockerproject.org/repo/main/centos/7
enabled=1
gpgcheck=1
gpgkey=https://yum.dockerproject.org/gpg
EOF

  # Add Docker systemd service
  sudo mkdir -p /etc/systemd/system/docker.service.d
  sudo tee /etc/systemd/system/docker.service.d/override.conf <<- EOF
[Service]
Restart=always
StartLimitInterval=0
RestartSec=15
ExecStartPre=-/sbin/ip link del docker0
ExecStart=
ExecStart=/usr/bin/dockerd --storage-driver=overlay --data-root=${docker_data_root}
EOF

  # Install and enable Docker
  sudo yum install -y docker-engine-17.05.0.ce docker-engine-selinux-17.05.0.ce
  sudo systemctl start docker
  sudo systemctl enable docker
fi

if ! sudo getent group nogroup >/dev/null; then
  echo "Creating 'nogroup' group..."
  sudo groupadd nogroup
fi

echo "Prerequisites installed."
"""
    # Run a first command to get json file generated.
    chain.add_execute(['echo', 'INSTALL', 'PREREQUISITES'], stage="Installing prerequisites")
    chain.add_execute([inline_script], stage='Installing preflight prerequisites')


@asyncio.coroutine
def install_prereqs(config, block=False, state_json_dir=None, async_delegate=None, options=None):
    targets = get_full_nodes_list(config)
    runner = get_async_runner(config, targets, async_delegate=async_delegate)
    prereqs_chain = ssh.utils.CommandChain('install_prereqs')
    _add_prereqs_script(prereqs_chain)
    result = yield from runner.run_commands_chain_async([prereqs_chain], block=block, state_json_dir=state_json_dir)
    return result
