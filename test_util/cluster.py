import itertools
import logging
import os
import stat
from contextlib import contextmanager

import passlib.hash
import pkg_resources
from retrying import retry

import gen.calc
import test_util.installer_api_test
import test_util.test_runner
from ssh.ssh_tunnel import SSHTunnel, TunnelCollection


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
        return SSHTunnel(self.user, self.key_path, host.public_ip)

    @contextmanager
    def tunnels(self, hosts):
        hostports = [host.public_ip + ':22' for host in hosts]
        with TunnelCollection(self.user, self.key_path, hostports) as tunnel_collection:
            yield tunnel_collection.tunnels

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
        # Make the default user priveleged to use docker
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

        with open(pkg_resources.resource_filename("gen", "ip-detect/aws.sh")) as ip_detect_fh:
            ip_detect_script = ip_detect_fh.read()
        with open(cluster.ssher.key_path, 'r') as key_fh:
            ssh_key = key_fh.read()
        # Using static exhibitor is the only option in the GUI installer
        if api:
            logging.info('Installer API is selected, so configure for static backend')
            zk_host = None  # causes genconf to use static exhibitor backend
        else:
            logging.info('Installer CLI is selected, so configure for ZK backend')
            zk_host = cluster.bootstrap_host.private_ip + ':2181'
            zk_cmd = [
                'sudo', 'docker', 'run', '-d', '-p', '2181:2181', '-p',
                '2888:2888', '-p', '3888:3888', 'jplock/zookeeper']
            bootstrap_host_tunnel.remote_cmd(zk_cmd)

        logging.info("Configuring install...")
        installer.genconf(
            zk_host=zk_host,
            master_list=[h.private_ip for h in cluster.masters],
            agent_list=[h.private_ip for h in cluster.agents],
            public_agent_list=[h.private_ip for h in cluster.public_agents],
            ip_detect_script=ip_detect_script,
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


def run_integration_tests(cluster, setup=True, **kwargs):
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
        return test_util.test_runner.integration_test(
            tunnel=test_tunnel,
            test_dir=cluster.ssher.home_dir,
            dcos_dns=cluster.masters[0].private_ip,
            master_list=[h.private_ip for h in cluster.masters],
            agent_list=[h.private_ip for h in cluster.agents],
            public_agent_list=[h.private_ip for h in cluster.public_agents],
            provider=cluster.provider,
            **kwargs)
