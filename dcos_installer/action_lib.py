import asyncio
import json
import logging
import os
from typing import Optional

import pkgpanda
import ssh.utils
from dcos_installer.constants import BOOTSTRAP_DIR, CHECK_RUNNER_CMD, CLUSTER_PACKAGES_PATH, SERVE_DIR, SSH_KEY_PATH
from ssh.runner import Node


REMOTE_TEMP_DIR = '/opt/dcos_install_tmp'

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
    chain.add_execute(['sudo', 'mkdir', '-p', REMOTE_TEMP_DIR], stage='Creating temp directory')
    chain.add_execute(['sudo', 'chown', ssh_user, REMOTE_TEMP_DIR],
                      stage='Ensuring {} owns temporary directory'.format(ssh_user))


def add_post_action(chain):
    # Do cleanup steps for a chain
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
def run_preflight(config, pf_script_path=(SERVE_DIR + '/dcos_install.sh'), block=False, state_json_dir=None,
                  async_delegate=None, retry=False, options=None):
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
    # In web mode run if no --offline flag used.
    if options.action == 'web':
        if options.offline:
            log.debug('Offline mode used. Do not install prerequisites on CentOS7, RHEL7 in web mode')
        else:
            _add_prereqs_script(preflight_chain)

    add_pre_action(preflight_chain, pf.user)
    preflight_chain.add_copy(pf_script_path, REMOTE_TEMP_DIR, stage='Copying preflight script')

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
    dcos_install_script = 'dcos_install.sh'
    local_install_path = os.path.join(local_install_path, dcos_install_script)
    remote_install_path = os.path.join(REMOTE_TEMP_DIR, dcos_install_script)
    chain.add_copy(local_install_path, remote_install_path, stage='Copying dcos_install.sh')


def _add_copy_packages(chain, local_pkg_base_path=SERVE_DIR):
    if not os.path.isfile(CLUSTER_PACKAGES_PATH):
        err_msg = '{} not found'.format(CLUSTER_PACKAGES_PATH)
        log.error(err_msg)
        raise ExecuteException(err_msg)

    cluster_packages = pkgpanda.load_json(CLUSTER_PACKAGES_PATH)
    for package, params in cluster_packages.items():
        destination_package_dir = os.path.join(REMOTE_TEMP_DIR, 'packages', package)
        local_pkg_path = os.path.join(local_pkg_base_path, params['filename'])

        chain.add_execute(['mkdir', '-p', destination_package_dir], stage='Creating package directory')
        chain.add_copy(local_pkg_path, destination_package_dir,
                       stage='Copying packages')


def _add_copy_bootstap(chain, local_bs_path):
    remote_bs_path = REMOTE_TEMP_DIR + '/bootstrap'
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
        'master': {
            'tags': {'role': 'master', 'dcos_install_param': 'master'},
            'hosts': config['master_list']
        },
        'agent': {
            'tags': {'role': 'agent', 'dcos_install_param': 'slave'},
            'hosts': config.hacky_default_get('agent_list', [])
        },
        'public_agent': {
            'tags': {'role': 'public_agent', 'dcos_install_param': 'slave_public'},
            'hosts': config.hacky_default_get('public_agent_list', [])
        }
    }

    bootstrap_tarball = _get_bootstrap_tarball()
    log.debug("Local bootstrap found: %s", bootstrap_tarball)

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
        pkgpanda_uninstall_chain.add_execute(['sudo', '-i', '/opt/mesosphere/bin/pkgpanda', 'uninstall'],
                                             stage='Trying pkgpanda uninstall')
        chains.append(pkgpanda_uninstall_chain)

        remove_dcos_chain = ssh.utils.CommandChain('remove_stale_dcos')
        remove_dcos_chain.add_execute(['rm', '-rf', '/opt/mesosphere', '/etc/mesosphere'],
                                      stage="Removing DC/OS files")
        chains.append(remove_dcos_chain)

    chain = ssh.utils.CommandChain('deploy')
    chains.append(chain)

    add_pre_action(chain, runner.user)
    _add_copy_dcos_install(chain)
    _add_copy_packages(chain)
    _add_copy_bootstap(chain, bootstrap_tarball)

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

    node_cleanup_chain = ssh.utils.CommandChain('postflight_cleanup')
    node_cleanup_chain.add_execute(
        ['sudo', 'rm', '-f', '/opt/dcos-prereqs.installed'],
        stage='Removing prerequisites flag')

    cluster_postflight_chain = ssh.utils.CommandChain('cluster_postflight')
    cluster_postflight_chain.add_execute(
        [cluster_check_script],
        stage='Executing cluster postflight checks')

    node_check_result = yield from node_runner.run_commands_chain_async(
        [node_postflight_chain, node_cleanup_chain],
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
    inline_script = """
#/bin/sh
# setenforce is in this path
PATH=$PATH:/sbin

dist=$(cat /etc/os-release | sed -n 's@^ID="\(.*\)"$@\\1@p')

if ([ x$dist == 'xcoreos' ]); then
  echo "Detected CoreOS. All prerequisites already installed" >&2
  exit 0
fi

if ([ x$dist != 'xrhel' ] && [ x$dist != 'xcentos' ]); then
  echo "$dist is not supported. Only RHEL and CentOS are supported" >&2
  exit 0
fi

version=$(cat /etc/*-release | sed -n 's@^VERSION_ID="\([0-9]*\)\([0-9\.]*\)"$@\1@p')
if [ $version -lt 7 ]; then
  echo "$version is not supported. Only >= 7 version is supported" >&2
  exit 0
fi

if [ -f /opt/dcos-prereqs.installed ]; then
  echo "install_prereqs has been already executed on this host, exiting..."
  exit 0
fi

sudo setenforce 0 && \
sudo sed -i --follow-symlinks 's/^SELINUX=.*/SELINUX=disabled/g' /etc/sysconfig/selinux

sudo tee /etc/yum.repos.d/docker.repo <<-'EOF'
[dockerrepo]
name=Docker Repository
baseurl=https://yum.dockerproject.org/repo/main/centos/7
enabled=1
gpgcheck=1
gpgkey=https://yum.dockerproject.org/gpg
EOF

sudo yum -y update --exclude="docker-engine*"

sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/override.conf <<- EOF
[Service]
Restart=always
StartLimitInterval=0
RestartSec=15
ExecStartPre=-/sbin/ip link del docker0
ExecStart=
ExecStart=/usr/bin/dockerd --storage-driver=overlay
EOF

sudo yum install -y docker-engine-1.13.1 docker-engine-selinux-1.13.1
sudo systemctl start docker
sudo systemctl enable docker

sudo yum install -y wget
sudo yum install -y git
sudo yum install -y unzip
sudo yum install -y curl
sudo yum install -y xz
sudo yum install -y ipset

sudo getent group nogroup || sudo groupadd nogroup
sudo touch /opt/dcos-prereqs.installed
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
