import copy
import logging
import subprocess

import pkg_resources
import retrying

import launch.aws
import launch.util

import test_util.aws
import test_util.onprem
import test_util.runner
from test_util.helpers import Url

log = logging.getLogger(__name__)

STATE_FILE = 'LAST_COMPLETED_STAGE'


@retrying.retry(wait_fixed=1000, stop_max_delay=120000)
def check_ssh(ssher, host, port):
    ssher.get_home_dir(host, port)


class OnpremLauncher(launch.util.AbstractLauncher):
    def __init__(self, config):
        # can only be set during the wait command
        self.bootstrap_host = None
        self.config = config

    def create(self):
        return self.get_bare_cluster_launcher().create()

    def post_state(self, state):
        self.get_ssher().command(self.bootstrap_host, ['printf', state, '>', STATE_FILE])

    def get_last_state(self):
        return self.get_ssher(self.config).command(self.bootstrap_host, ['cat', STATE_FILE]).decode().strip()

    def get_bare_cluster_launcher(self):
        if self.config['platform'] == 'aws':
            return launch.aws.BareClusterLauncher(self.config)
        else:
            raise launch.util.LauncherError('Platform currently not supported for onprem: {}'.format(
                self.config['platform']))

    def get_onprem_cluster(self):
        return test_util.onprem.OnpremCluster.from_hosts(
            ssher=self.get_ssher(),
            hosts=self.get_bare_cluster_launcher().get_hosts(),
            num_masters=int(self.config['num_masters']),
            num_private_agents=int(self.config['num_private_agents']),
            num_public_agents=int(self.config['num_public_agents']))

    def get_completed_onprem_config(self, cluster: test_util.onprem.OnpremCluster) -> dict:
        onprem_config = self.config['dcos_config']
        # First, try and retrieve the agent list from the cluster
        onprem_config['agent_list'] = [h.private_ip for h in cluster.private_agents]
        onprem_config['public_agent_list'] = [h.private_ip for h in cluster.public_agents]
        onprem_config['master_list'] = [h.private_ip for h in cluster.masters]
        # if the user wanted to use exhibitor as the backend, then start it
        if onprem_config.get('exhibitor_storage_backend') == 'zookeeper':
            onprem_config['exhibitor_zk_hosts'] = cluster.start_bootstrap_zk()
        # if key helper is true then ssh key must be injected, or the key
        # must have been provided as a file and still needs to be injected
        if self.config['key_helper'] or 'ssh_key' not in onprem_config:
            onprem_config['ssh_key'] = self.config['ssh_private_key']
        # check if ssh user was not provided
        if 'ssh_user' not in onprem_config:
            onprem_config['ssh_user'] = self.config['ssh_user']
        # check if the user provided any filenames and convert them into content
        for key_name in ('ip_detect_filename', 'ip_detect_public_filename'):
            if key_name not in onprem_config:
                continue
            new_key_name = key_name.replace('_filename', '_contents')
            if new_key_name in onprem_config:
                raise launch.util.LauncherError(
                    'InvalidDcosConfig', 'Cannot set *_filename and *_contents simultaneously!')
            onprem_config[new_key_name] = launch.util.load_string(onprem_config[key_name])
            del onprem_config[key_name]
        # set the simple default IP detect script if not provided
        # currently, only AWS is supported, but when support changes, this will have to update
        if 'ip_detect_contents' not in onprem_config:
            onprem_config['ip_detect_contents'] = pkg_resources.resource_string(
                'launch', 'ip-detect/aws.sh').decode('utf-8')
        if 'ip_detect_contents' not in onprem_config:
            onprem_config['ip_detect_public_contents'] = pkg_resources.resource_string(
                'launch', 'ip-detect/aws_public.sh').decode('utf-8')
        # For no good reason the installer uses 'ip_detect_script' instead of 'ip_detect_contents'
        onprem_config['ip_detect_script'] = self.config['dcos_config']['ip_detect_contents']
        del onprem_config['ip_detect_contents']
        log.debug('Generated cluster configuration: {}'.format(onprem_config))
        return onprem_config

    def wait(self):
        log.info('Waiting for bare cluster provisioning status..')
        self.get_bare_cluster_launcher().wait()
        cluster = self.get_onprem_cluster()
        self.bootstrap_host = cluster.bootstrap_host.public_ip
        log.info('Waiting for SSH connectivity to bootstrap host...')
        check_ssh(self.get_ssher(), self.bootstrap_host, self.config['ssh_port'])
        try:
            self.get_ssher().command(self.bootstrap_host, ['test', '-f', STATE_FILE])
            last_complete = self.get_last_state()
        except subprocess.CalledProcessError:
            last_complete = None

        if last_complete is None:
            cluster.setup_installer_server(self.config['installer_url'], False)
            last_complete = 'SETUP'
            self.post_state(last_complete)

        installer = test_util.onprem.DcosInstallerApiSession(Url(
            'http', self.bootstrap_host, '', '', '', self.config['installer_port']))
        if last_complete == 'SETUP':
            last_complete = 'GENCONF'
            installer.genconf(self.get_completed_onprem_config(cluster))
            self.post_state(last_complete)
        if last_complete == 'GENCONF':
            installer.preflight()
            last_complete = 'PREFLIGHT'
            self.post_state(last_complete)
        if last_complete == 'PREFLIGHT':
            installer.deploy()
            last_complete = 'DEPLOY'
            self.post_state(last_complete)
        if last_complete == 'DEPLOY':
            installer.postflight()
            last_complete = 'POSTFLIGHT'
            self.post_state(last_complete)
        if last_complete != 'POSTFLIGHT':
            raise launch.util.LauncherError('InconsistentState', 'State on bootstrap host is: ' + last_complete)

    def describe(self):
        """ returns host information stored in the config as
        well as the basic provider info
        """
        cluster = self.get_onprem_cluster()
        extra_info = {
            'bootstrap_host': launch.util.convert_host_list([cluster.bootstrap_host])[0],
            'masters': launch.util.convert_host_list(cluster.get_master_ips()),
            'private_agents': launch.util.convert_host_list(cluster.get_private_agent_ips()),
            'public_agents': launch.util.convert_host_list(cluster.get_public_agent_ips())}
        desc = copy.copy(self.config)
        desc.update(extra_info)
        # blackout unwanted fields
        del desc['template_body']
        del desc['template_parameters']
        return desc

    def delete(self):
        """ just deletes the hardware
        """
        self.get_bare_cluster_launcher().delete()
