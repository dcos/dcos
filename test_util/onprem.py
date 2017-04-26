""" Utilities to assist with orchestrating and testing an onprem deployment
"""
import copy
import itertools
import logging
from typing import List

import requests
from retrying import retry

from ssh.ssher import Ssher
from test_util.helpers import ApiClientSession, Host, Url


log = logging.getLogger(__name__)


def log_and_raise_if_not_ok(response: requests.Response):
    if not response.ok:
        log.error(response.content.decode())
        response.raise_for_status()


class OnpremCluster:

    def __init__(
            self,
            ssher: Ssher,
            masters: List[Host],
            private_agents: List[Host],
            public_agents: List[Host],
            bootstrap_host: Host):
        """ An abstration for an arbitrary group of servers to be used
        as bootstrapping node and deployment nodes for DC/OS
        Args:
            ssher: Ssher object for accessing any given node in the cluster
            masters: list of Hosts tuples to be used as masters
            private_agents: list of Host tuples to be used as private agents
            public_agents: list of Host tuples to be used as public agents
            bootstrap_host: Host tuple for the bootstrap host I.E. has installer
                downloaded to it and perhaps hosts a bootstrap ZooKeeper
        """
        self.ssher = ssher
        self.masters = masters
        self.private_agents = private_agents
        self.public_agents = public_agents
        self.bootstrap_host = bootstrap_host
        assert all(h.private_ip for h in self.hosts), (
            'All cluster hosts require a private IP. hosts: {}'.format(repr(self.hosts))
        )

    def get_master_ips(self):
        return copy.copy(self.masters)

    def get_private_agent_ips(self):
        return copy.copy(self.private_agents)

    def get_public_agent_ips(self):
        return copy.copy(self.public_agents)

    @classmethod
    def from_hosts(cls, ssher, hosts, num_masters, num_private_agents, num_public_agents):
        bootstrap_host, masters, private_agents, public_agents = (
            cls.partition_cluster(hosts, num_masters, num_private_agents, num_public_agents))

        return cls(
            ssher=ssher,
            masters=masters,
            private_agents=private_agents,
            public_agents=public_agents,
            bootstrap_host=bootstrap_host,
        )

    @property
    def hosts(self):
        return self.masters + self.private_agents + self.public_agents + (
            [self.bootstrap_host] if self.bootstrap_host else []
        )

    @staticmethod
    def partition_cluster(
            hosts: List[Host],
            num_masters: int,
            num_agents: int,
            num_public_agents: int):
        """Return (bootstrap, masters, agents, public_agents) from hosts."""
        hosts_iter = iter(sorted(hosts))
        return (
            next(hosts_iter),
            list(itertools.islice(hosts_iter, num_masters)),
            list(itertools.islice(hosts_iter, num_agents)),
            list(itertools.islice(hosts_iter, num_public_agents)),
        )

    def start_bootstrap_zk(self):
        zk_host = self.bootstrap_host.private_ip + ':2181'
        self.ssher.command(
            self.bootsrap_host.private_ip,
            ['docker', 'run', '--name', 'dcos-bootstrap-zk', '--detach=true',
             '--publish=2181:2181', '--publish=2888:2888', '--publish=3888:3888', 'jplock/zookeeper'])
        return zk_host

    def setup_installer_server(self, installer_url: str, offline_mode: bool):
        log.info('Setting up installer on bootstrap host')
        return DcosInstallerApiSession.api_session_from_host(
            self.ssher, self.bootstrap_host.public_ip, installer_url, offline_mode)


@retry(wait_fixed=3000, stop_max_delay=300 * 1000)
def _download_dcos_installer(ssher, host, installer_path, download_url):
    """Response status 403 is fatal for curl's retry. Additionally, S3 buckets
    have been returning 403 for valid uploads for 10-15 minutes after CI finished build
    Therefore, give a five minute buffer to help stabilize CI
    """
    log.info('Attempting to download installer from: ' + download_url)
    try:
        ssher.command(host, ['curl', '-fLsSv', '--retry', '20', '-Y', '100000', '-y', '60',
                      '--create-dirs', '-o', installer_path, download_url])
    except:
        log.exception('Download failed!')
        raise


class DcosInstallerApiSession(ApiClientSession):
    @classmethod
    def api_session_from_host(
            cls,
            ssher: Ssher,
            host: str,
            installer_url: str,
            offline_mode: bool,
            port: int=9000):
        """ Will download and start a DC/OS onprem installer and return a
        DcosInstallerApiSession to interact with it

        Args:
            ssher: Ssher object to access the server hosting the installer
            host: IP address of the target host server
            installer_url: URL to pull the installer from relative to the host
            offline_mode: if True, installer will start with the --offline-mode
                option which disables installing pre-requisites from the internet
            port: the installer can run on an arbitrary port but defaults to 9000
        """
        ssher.command(host, ['sudo', 'usermod', '-aG', 'docker', ssher.user])

        host_home = ssher.get_home_dir(host)
        installer_path = host_home + '/dcos_generate_config.sh'

        _download_dcos_installer(ssher, host, installer_path, installer_url)

        log.info('Starting installer server at: {}:{}'.format(host, port))
        cmd = ['DCOS_INSTALLER_DAEMONIZE=true', 'bash', installer_path, '--web', '-p', str(port)]
        if offline_mode:
            cmd.append('--offline')
        ssher.command(host, cmd)

        api = cls(Url('http', host, '', '', '', port))

        @retry(wait_fixed=1000, stop_max_delay=60000)
        def wait_for_up():
            log.debug('Waiting for installer server...')
            api.get('/').raise_for_status()

        wait_for_up()
        log.info('Installer server is up and running!')
        return api

    def genconf(self, config):
        log.info('Generating configuration on installer server...')
        response = self.post('/api/v1/configure', json=config)
        log_and_raise_if_not_ok(response)
        response_json = response.json()
        if 'error' in response_json:
            # genconf was unsuccessful
            raise Exception('Error generating configuration: {}'.format(response_json['error']))
        return response_json

    def preflight(self) -> None:
        log.info('Starting preflight...')
        self.do_and_check('preflight')

    def deploy(self) -> None:
        log.info('Starting deploy...')
        self.do_and_check('deploy')

    def postflight(self) -> None:
        log.info('Starting postflight...')
        self.do_and_check('postflight')

    def do_and_check(self, action: str) -> None:
        """Args:
            action (str): one of 'preflight', 'deploy', 'postflight'
        """
        self.start_action(action)
        self.wait_for_check_action(action)

    def wait_for_check_action(self, action: str) -> None:
        """Retries method against API until returned data shows that all hosts
        have finished. No timeout necessary as the installer sets its own timeout

        Args:
            action (str): choies are 'preflight', 'deploy', 'postflight'
        """
        @retry(
            wait_fixed=10000,
            retry_on_result=lambda res: res is False,
            retry_on_exception=lambda ex: False)
        def wait_for_finish():
            output = self.check_action(action)
            host_data = output['hosts']
            finished_run = all(map(lambda host: host['host_status'] not in ['running', 'unstarted'],
                                   host_data.values()))
            if not finished_run:
                log.info('Processes not yet finished, continuing to wait...')
                return False
            return host_data

        host_data = wait_for_finish()
        failures = list()
        for host in host_data.keys():
            if host_data[host]['host_status'] != 'success':
                failures.append(host_data[host])
        if len(failures) > 0:
            raise Exception("Failures detected in {}: {}".format(action, failures))

    def start_action(self, action: str) -> None:
        """Args:
            action (str): one of 'preflight', 'deploy', 'postflight'
        """
        log_and_raise_if_not_ok(self.post('/api/v1/action/{}'.format(action)))

    def check_action(self, action: str) -> dict:
        """Args:
            action (str): one of 'preflight', 'deploy', 'postflight', 'success'
        """
        log.debug('Checking status of action: {}'.format(action))
        r = self.get('/api/v1/action/{}'.format(action))
        log_and_raise_if_not_ok(r)
        return r.json()
