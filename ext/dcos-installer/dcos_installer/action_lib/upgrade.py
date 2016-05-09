import asyncio
import json
import logging
import os

from ssh.ssh_runner import Node
import ssh.utils

from .utils import REMOTE_TEMP_DIR, CLUSTER_PACKAGES_FILE, get_async_runner, add_post_action, add_pre_action

log = logging.getLogger(__name__)


@asyncio.coroutine
def upgrade(config, block=False, state_json_dir=None, hosts=[], async_delegate=None, try_remove_stale_dcos=False,
                 roles=None, **kwargs):
    """Upgrdes a host by copying over new packages to the dcos install_tmp directory, then executing pkpanda
    fetch and pkgpanda switch.
    In order to ensure fault tolerance, upon failed command chain the try_remote_stale_dcos will mv the backed up
    pkgs back, and re-run pkgpanda fetch && switch to ensure we can fall back in case of failed copy or
    upgrade interuption.
    """

    if roles is None:
        roles = ['master', 'agent']

    targets = []
    for role in roles:
        default_params = role_params[role]
        for host in default_params['hosts']:
            node = Node(host, default_params['tags'])
            targets += [node]

    log.debug('Got {} hosts'.format(targets))
    runner = get_async_runner(config, targets, async_delegate=async_delegate)
    chains = []
    if try_remove_stale_dcos:
        pkgpanda_uninstall_chain = ssh.utils.CommandChain('remove_stale_dcos')
        pkgpanda_uninstall_chain.add_execute(['sudo', '-i', '/opt/mesosphere/bin/pkgpanda', 'uninstall'],
                                             comment='TRYING pkgpanda uninstall')
        chains.append(pkgpanda_uninstall_chain)

        remove_dcos_chain = ssh.utils.CommandChain('remove_stale_dcos')
        remove_dcos_chain.add_execute(['rm', '-rf', '/opt/mesosphere', '/etc/mesosphere'])
        chains.append(remove_dcos_chain)

    chain = ssh.utils.CommandChain('upgrade')
    chains.append(chain)

    add_pre_action(chain, runner.ssh_user)
    _add_copy_packages(chain)

    # TODO stopping here, need specific pkpanda commands to execute on host run. Need to implement fault tolerant
    # cleanup
    chain.add_execute(
        lambda node: (
            'sudo bash {}/dcos_install.sh {}'.format(REMOTE_TEMP_DIR, node.tags['dcos_install_param'])).split(),
        comment=lambda node: 'INSTALLING DC/OS ON NODE {}, ROLE {}'.format(node.ip, node.tags['role'])
    )

    # UI expects total_masters, total_agents to be top level keys in deploy.json
    delegate_extra_params = {
        'total_masters': len(config['master_list']),
        'total_agents': len(config['agent_list'])
    }
    if kwargs.get('retry') and state_json_dir:
        state_file_path = os.path.join(state_json_dir, 'deploy.json')
        log.debug('retry executed for a state file deploy.json')
        for _host in hosts:
            _remove_host(state_file_path, _host)

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


