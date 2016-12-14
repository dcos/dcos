import itertools
import json
import logging
import os
import random
import stat
from contextlib import contextmanager
from subprocess import CalledProcessError

import passlib.hash
from retrying import retry, RetryError

import gen.calc
import test_util.installer_api_test
import test_util.runner
from ssh.tunnel import tunnel, tunnel_collection


zookeeper_docker_image = 'jplock/zookeeper'
zookeeper_docker_run_args = ['--publish=2181:2181', '--publish=2888:2888', '--publish=3888:3888']

curl_cmd = [
    'curl',
    '--silent',
    '--verbose',
    '--show-error',
    '--fail',
    '--location',
    '--keepalive-time', '2',
    '--retry', '20',
    '--speed-limit', '100000',
    '--speed-time', '60',
]


class Ssher:

    def __init__(self, user, home_dir, key_path):
        self.user = user
        self.home_dir = home_dir
        self.key_path = key_path

        try:
            os.chmod(self.key_path, stat.S_IREAD | stat.S_IWRITE)
        except FileNotFoundError as exc:
            raise Exception('SSH key not found at path {}'.format(self.key_path)) from exc
        except OSError as exc:
            raise Exception('Unable to set permissions on SSH key at {}: {}'.format(
                self.key_path,
                exc,
            )) from exc

    def tunnel(self, host):
        return tunnel(self.user, self.key_path, host.public_ip)

    @contextmanager
    def tunnels(self, hosts):
        hostports = [host.public_ip + ':22' for host in hosts]
        with tunnel_collection(self.user, self.key_path, hostports) as tunnels:
            yield tunnels

    def remote_cmd(self, hosts, cmd):
        with self.tunnels(hosts) as tunnels:
            for tunnel in tunnels:
                tunnel.remote_cmd(cmd)


class Cluster:

    def __init__(
        self,
        ssh_info,
        ssh_key_path,
        provider,
        masters,
        agents,
        public_agents,
        bootstrap_host=None,
    ):
        # Assert that this is a valid cluster.
        gen.calc.validate_num_masters(str(len(masters)))

        self.ssher = Ssher(ssh_info.user, ssh_info.home_dir, ssh_key_path)
        self.provider = provider
        self.masters = masters
        self.agents = agents
        self.public_agents = public_agents
        self.bootstrap_host = bootstrap_host

        assert all(h.private_ip for h in self.hosts), (
            'All cluster hosts require a private IP. hosts: {}'.format(repr(self.hosts))
        )

        if self.provider == 'onprem':
            self.check_ssh(self.hosts)
        else:
            self.check_ssh(self.masters)

        logging.info('Bootstrap host: ' + repr(self.bootstrap_host))
        logging.info('Masters: ' + repr(self.masters))
        logging.info('Agents: ' + repr(self.agents))
        logging.info('Public agents: ' + repr(self.public_agents))

    @classmethod
    def from_hosts(
        cls,
        ssh_info,
        ssh_key_path,
        hosts,
        num_masters,
        num_agents,
        num_public_agents,
    ):
        assert all(x >= 0 for x in [num_masters, num_agents, num_public_agents]), (
            'num_masters, num_agents, and num_public_agents must be 0 or greater. '
            'num_masters: {num_masters}, num_agents: {num_agents}, num_public_agents: {num_public_agents}'.format(
                num_masters=num_masters,
                num_agents=num_agents,
                num_public_agents=num_public_agents,
            )
        )
        assert len(hosts) == num_masters + num_agents + num_public_agents + 1, (
            'Number of hosts must be equal to sum of masters and agents plus the bootstrap host.'
            'num_masters: {num_masters}, num_agents: {num_agents}, num_public_agents: {num_public_agents}, '
            'hosts: {hosts}'.format(
                num_masters=num_masters,
                num_agents=num_agents,
                num_public_agents=num_public_agents,
                hosts=repr(hosts),
            )
        )

        bootstrap_host, masters, agents, public_agents = (
            cls.partition_cluster(hosts, num_masters, num_agents, num_public_agents)
        )

        return cls(
            ssh_info=ssh_info,
            ssh_key_path=ssh_key_path,
            provider='onprem',
            masters=masters,
            agents=agents,
            public_agents=public_agents,
            bootstrap_host=bootstrap_host,
        )

    @classmethod
    def from_vpc(
        cls,
        vpc,
        ssh_info,
        ssh_key_path,
        num_masters,
        num_agents,
        num_public_agents,
    ):
        hosts = vpc.get_vpc_host_ips()
        logging.info('AWS provided VPC info: ' + repr(hosts))

        return cls.from_hosts(
            ssh_info=ssh_info,
            ssh_key_path=ssh_key_path,
            hosts=hosts,
            num_masters=num_masters,
            num_agents=num_agents,
            num_public_agents=num_public_agents,
        )

    @classmethod
    def from_cloudformation(cls, cf, ssh_info, ssh_key_path):
        return cls(
            ssh_info=ssh_info,
            ssh_key_path=ssh_key_path,
            provider='aws',
            masters=cf.get_master_ips(),
            agents=cf.get_private_agent_ips(),
            public_agents=cf.get_public_agent_ips(),
        )

    @property
    def hosts(self):
        return self.masters + self.agents + self.public_agents + (
            [self.bootstrap_host] if self.bootstrap_host else []
        )

    @staticmethod
    def partition_cluster(hosts, num_masters, num_agents, num_public_agents):
        """Return (bootstrap, masters, agents, public_agents) from hosts."""
        hosts_iter = iter(hosts)
        return (
            next(hosts_iter),
            list(itertools.islice(hosts_iter, num_masters)),
            list(itertools.islice(hosts_iter, num_agents)),
            list(itertools.islice(hosts_iter, num_public_agents)),
        )

    @retry(stop_max_delay=120000)
    def check_ssh(self, hosts):
        """SSH to each host's public IP and run a command.

        Retries on failure for up to 2 minutes.

        """
        self.ssher.remote_cmd(hosts, ['echo'])

    def mesos_metrics_snapshot(self, host):
        """Return a snapshot of the Mesos metrics for host."""
        if host in self.masters:
            port = 5050
        else:
            port = 5051

        with self.ssher.tunnel(host) as tunnel:
            return json.loads(
                tunnel.remote_cmd(
                    curl_cmd + ['{}:{}/metrics/snapshot'.format(host.private_ip, port)]
                ).decode('utf-8')
            )


def run_docker_container_daemon(tunnel, container_name, image, docker_run_args=None):
    """Run a Docker container with the given name on the host at tunnel."""
    docker_run_args = docker_run_args or []
    tunnel.remote_cmd(
        ['docker', 'run', '--name', container_name, '--detach=true'] + docker_run_args + [image]
    )


def run_bootstrap_zookeeper(tunnel):
    """Run the bootstrap ZooKeeper daemon on the host at tunnel."""
    run_docker_container_daemon(
        tunnel,
        'dcos-bootstrap-zk',
        zookeeper_docker_image,
        zookeeper_docker_run_args,
    )


def run_bootstrap_nginx(tunnel, home_dir):
    """Run the bootstrap Nginx daemon on the host at tunnel."""
    run_docker_container_daemon(
        tunnel,
        'dcos-bootstrap-nginx',
        'nginx',
        ['--publish=80:80', '--volume={}/genconf/serve:/usr/share/nginx/html:ro'.format(home_dir)],
    )


def install_dcos(
    cluster,
    installer_url,
    api=False,
    setup=True,
    add_config_path=None,
    installer_api_offline_mode=True,
    install_prereqs=True,
    install_prereqs_only=False,
):
    if cluster.provider != 'onprem':
        raise NotImplementedError('Install is only supported for onprem clusters')

    assert cluster.bootstrap_host is not None, 'Install requires a bootstrap host'
    assert all(h.public_ip for h in cluster.hosts), (
        'Install requires that all cluster hosts have a public IP. hosts: {}'.format(repr(cluster.hosts))
    )

    if api:
        installer = test_util.installer_api_test.DcosApiInstaller()
        installer.offline_mode = installer_api_offline_mode
    else:
        installer = test_util.installer_api_test.DcosCliInstaller()

    if setup:
        # Make the default user privileged to use docker
        cluster.ssher.remote_cmd(
            [cluster.bootstrap_host],
            ['sudo', 'usermod', '-aG', 'docker', cluster.ssher.user],
        )

    with cluster.ssher.tunnel(cluster.bootstrap_host) as bootstrap_host_tunnel:
        logging.info('Setting up installer on bootstrap host')

        installer.setup_remote(
            tunnel=bootstrap_host_tunnel,
            installer_path=cluster.ssher.home_dir + '/dcos_generate_config.sh',
            download_url=installer_url)
        if setup:
            # only do on setup so you can rerun this test against a living installer
            logging.info('Verifying installer password hashing')
            test_pass = 'testpassword'
            hash_passwd = installer.get_hashed_password(test_pass)
            assert passlib.hash.sha512_crypt.verify(test_pass, hash_passwd), 'Hash does not match password'
            if api:
                installer.start_web_server()

        with open(cluster.ssher.key_path, 'r') as key_fh:
            ssh_key = key_fh.read()
        # Using static exhibitor is the only option in the GUI installer
        if api:
            logging.info('Installer API is selected, so configure for static backend')
            zk_host = None  # causes genconf to use static exhibitor backend
        else:
            logging.info('Installer CLI is selected, so configure for ZK backend')
            run_bootstrap_zookeeper(bootstrap_host_tunnel)
            zk_host = cluster.bootstrap_host.private_ip + ':2181'

        logging.info("Configuring install...")
        installer.genconf(
            zk_host=zk_host,
            master_list=[h.private_ip for h in cluster.masters],
            agent_list=[h.private_ip for h in cluster.agents],
            public_agent_list=[h.private_ip for h in cluster.public_agents],
            ip_detect='aws',
            ssh_user=cluster.ssher.user,
            ssh_key=ssh_key,
            add_config_path=add_config_path,
            rexray_config_preset='aws')

        logging.info("Running Preflight...")
        if install_prereqs:
            # Runs preflight in --web or --install-prereqs for CLI
            # This may take up 15 minutes...
            installer.install_prereqs()
            if install_prereqs_only:
                return
        else:
            # Will not fix errors detected in preflight
            installer.preflight()

        logging.info("Running Deploy...")
        installer.deploy()

        logging.info("Running Postflight")
        installer.postflight()


def upgrade_dcos(cluster, installer_url, add_config_path=None):

    def upgrade_host(tunnel, role, bootstrap_url):
        # Download the install script for the new DC/OS.
        tunnel.remote_cmd(curl_cmd + ['--remote-name', bootstrap_url + '/dcos_install.sh'])

        # Remove the old DC/OS.
        tunnel.remote_cmd(['sudo', '-i', '/opt/mesosphere/bin/pkgpanda', 'uninstall'])
        tunnel.remote_cmd(['sudo', 'rm', '-rf', '/opt/mesosphere', '/etc/mesosphere'])

        # Install the new DC/OS.
        tunnel.remote_cmd(['sudo', 'bash', 'dcos_install.sh', '-d', role])

    @retry(
        wait_fixed=(1000 * 5),
        stop_max_delay=(1000 * 60 * 5),
        # Retry on SSH command error or metric not equal to expected value.
        retry_on_exception=(lambda exc: isinstance(exc, CalledProcessError)),
        retry_on_result=(lambda result: not result),
    )
    def wait_for_mesos_metric(cluster, host, key, value):
        """Return True when host's Mesos metric key is equal to value."""
        return cluster.mesos_metrics_snapshot(host).get(key) == value

    assert all(h.public_ip for h in cluster.hosts), (
        'All cluster hosts must be externally reachable. hosts: {}'.formation(cluster.hosts)
    )
    assert cluster.bootstrap_host, 'Upgrade requires a bootstrap host'

    bootstrap_url = 'http://' + cluster.bootstrap_host.private_ip

    logging.info('Preparing bootstrap host for upgrade')
    with open(cluster.ssher.key_path, 'r') as key_fh:
        ssh_key = key_fh.read()
    installer = test_util.installer_api_test.DcosCliInstaller()
    with cluster.ssher.tunnel(cluster.bootstrap_host) as bootstrap_host_tunnel:
        installer.setup_remote(
            tunnel=bootstrap_host_tunnel,
            installer_path=cluster.ssher.home_dir + '/dcos_generate_config.sh',
            download_url=installer_url,
        )
        installer.genconf(
            bootstrap_url=bootstrap_url,
            zk_host=cluster.bootstrap_host.private_ip + ':2181',
            master_list=[h.private_ip for h in cluster.masters],
            agent_list=[h.private_ip for h in cluster.agents],
            public_agent_list=[h.private_ip for h in cluster.public_agents],
            ip_detect='aws',
            ssh_user=cluster.ssher.user,
            ssh_key=ssh_key,
            add_config_path=add_config_path,
            rexray_config_preset='aws',
        )
        # Remove docker (and associated journald) restart from the install
        # script. This prevents Docker-containerized tasks from being killed
        # during agent upgrades.
        bootstrap_host_tunnel.remote_cmd([
            'sudo', 'sed',
            '-i',
            '-e', '"s/systemctl restart systemd-journald//g"',
            '-e', '"s/systemctl restart docker//g"',
            cluster.ssher.home_dir + '/genconf/serve/dcos_install.sh',
        ])
        run_bootstrap_nginx(bootstrap_host_tunnel, cluster.ssher.home_dir)

    upgrade_ordering = [
        # Upgrade masters in a random order.
        ('master', 'master', random.sample(cluster.masters, len(cluster.masters))),
        ('slave', 'agent', cluster.agents),
        ('slave_public', 'public agent', cluster.public_agents),
    ]
    logging.info('\n'.join(
        ['Upgrade plan:'] +
        ['{} ({})'.format(host, role_name) for _, role_name, hosts in upgrade_ordering for host in hosts]
    ))
    for role, role_name, hosts in upgrade_ordering:
        logging.info('Upgrading {} nodes: {}'.format(role_name, repr(hosts)))
        for host in hosts:
            logging.info('Upgrading {}: {}'.format(role_name, repr(host)))
            with cluster.ssher.tunnel(host) as tunnel:
                upgrade_host(tunnel, role, bootstrap_url)

            wait_metric = {
                'master': 'registrar/log/recovered',
                'slave': 'slave/registered',
                'slave_public': 'slave/registered',
            }[role]
            logging.info('Waiting for {} to rejoin the cluster...'.format(role_name))
            try:
                wait_for_mesos_metric(cluster, host, wait_metric, 1)
            except RetryError as exc:
                raise Exception(
                    'Timed out waiting for {} to rejoin the cluster after upgrade: {}'.format(role_name, repr(host))
                ) from exc


def run_integration_tests(cluster, **kwargs):
    assert len(cluster.agents) >= 2 and len(cluster.public_agents) >= 1, (
        'Tests require 2 agents and 1 public agent. agents: {agents}, public_agents: {public_agents}'.format(
            agents=repr(cluster.agents),
            public_agents=repr(cluster.public_agents),
        )
    )
    assert any(h.public_ip for h in cluster.masters), (
        'At least one master must be externally reachable. masters: {}'.format(repr(cluster.masters))
    )

    test_host = next(m for m in cluster.masters if m.public_ip)
    logging.info('Test host: ' + repr(test_host))

    with cluster.ssher.tunnel(test_host) as test_tunnel:
        return test_util.runner.integration_test(
            tunnel=test_tunnel,
            test_dir=cluster.ssher.home_dir,
            dcos_dns=cluster.masters[0].private_ip,
            master_list=[h.private_ip for h in cluster.masters],
            agent_list=[h.private_ip for h in cluster.agents],
            public_agent_list=[h.private_ip for h in cluster.public_agents],
            provider=cluster.provider,
            **kwargs)
