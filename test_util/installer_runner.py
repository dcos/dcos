"""Python API for interacting with installer API
"""
import abc
import json
import logging
import os
import passlib.hash
import pkg_resources
from contextlib import closing
from subprocess import CalledProcessError

import requests
import yaml
from retrying import retry

import test_util.test_runner
from ssh.ssh_tunnel import SSHTunnel, run_scp_cmd, run_ssh_cmd

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
log = logging.getLogger(__name__)


class AbstractDcosInstaller(metaclass=abc.ABCMeta):

    def __init__(self):
        pass

    def setup_remote(
            self, tunnel, installer_path, download_url,
            host=None, ssh_user=None, ssh_key_path=None):
        """Creates a light, system-based ssh handler
        Args:
            tunnel: SSHTunnel instance to avoid recreating SSH connections.
                If set to None, ssh_user, host, and ssh_key_path must be
                set and one-off connections will be made
            installer_path: (str) path on host to download installer to
            download_url: (str) URL that installer can be pulled from
            host: (str) where the installer will be downloaded to
            ssh_user: (str) user with access to host
            ssh_key_path: (str) path to valid ssh key for ssh_user@host
        """
        self.installer_path = installer_path
        if tunnel:
            assert isinstance(tunnel, SSHTunnel)
            self.tunnel = tunnel
            self.url = "http://{}:9000".format(tunnel.host)

            def ssh(cmd):
                return tunnel.remote_cmd(cmd)

            def scp(src, dst):
                return tunnel.write_to_remote(src, dst)

        else:
            assert ssh_user, 'ssh_user must be set if tunnel not set'
            assert ssh_key_path, 'ssh_key_path must be set if tunnel not set'
            assert host, 'host must be set if tunnel not set'
            self.url = "http://{}:9000".format(host)

            def ssh(cmd):
                return run_ssh_cmd(ssh_user, ssh_key_path, host, cmd)

            def scp(src, dst):
                return run_scp_cmd(ssh_user, ssh_key_path, host, src, dst)

        self.ssh = ssh
        self.scp = scp

        if download_url:
            self.ssh(['curl', '-fLsSv', '--retry', '20', '-Y', '100000', '-y', '60',
                      '--create-dirs', '-o', self.installer_path, download_url])

    def get_hashed_password(self, password):
        p = self.ssh(["bash", self.installer_path, "--hash-password", password])
        # password hash is last line output but output ends with newline
        passwd_hash = p.decode('utf-8').split('\n')[-2]
        return passwd_hash

    @abc.abstractmethod
    def genconf(self, expect_errors=False):
        pass

    @abc.abstractmethod
    def preflight(self, expect_errors=False):
        pass

    @abc.abstractmethod
    def install_prereqs(self, expect_errors=False):
        pass

    @abc.abstractmethod
    def deploy(self, expect_errors=False):
        pass

    @abc.abstractmethod
    def postflight(self, expect_errors=False):
        pass


class DcosApiInstaller(AbstractDcosInstaller):

    def __init__(self, offline_mode):
        super().__init__(self)
        self.offline_mode = offline_mode

    def start_web_server(self):
        cmd = ['DCOS_INSTALLER_DAEMONIZE=true', 'bash', self.installer_path, '--web']
        if self.offline_mode:
            cmd.append('--offline')
        self.ssh(cmd)

        @retry(wait_fixed=1000, stop_max_delay=10000)
        def wait_for_up():
            assert requests.get(self.url).status_code == 200
            print("Webserver started")

        wait_for_up()

    def genconf(
            self, master_list, agent_list, public_agent_list, ssh_user, ssh_key,
            ip_detect_script, zk_host=None, expect_errors=False, add_config_path=None):
        """Runs configuration generation.

        Args:
            master_list: list of IPv4 addresses to be used as masters
            agent_list: list of IPv4 addresses to be used as agents
            public_agent_list: list of IPv4 addresses to be used as public agents
            ip_detect_script (str): complete contents of IP-detect script
            ssh_user (str): name of SSH user that has access to targets
            ssh_key (str): complete public SSH key for ssh_user. Must already
                be installed on tagets as authorized_key
            zk_host (optional): if provided, zk is used for exhibitor backend
            expect_errors (optional): raises error if result is unexpected
            add_config_path (optional): string pointing to a file with additional
                config parameters to be merged or used as overide

        Raises:
            AssertionError: "error" present in returned json keys when error
                was not expected or vice versa
        """
        headers = {'content-type': 'application/json'}
        payload = {
            'master_list': master_list,
            'agent_list': agent_list,
            'public_agent_list': public_agent_list,
            'ssh_user': ssh_user,
            'ssh_key': ssh_key,
            'ip_detect_script': ip_detect_script}
        if zk_host:
            payload['exhibitor_zk_hosts'] = zk_host
        if add_config_path:
            with open(add_config_path, 'r') as fh:
                add_config = yaml.load(fh)
            payload.update(add_config)
        response = requests.post(self.url + '/api/v1/configure', headers=headers, data=json.dumps(payload))
        assert response.status_code == 200
        response_json_keys = list(response.json().keys())
        if expect_errors:
            assert "error" in response_json_keys
        else:
            assert "error" not in response_json_keys

    def install_prereqs(self, expect_errors=False):
        assert not self.offline_mode, "Install prereqs can only be run without --offline mode"
        self.preflight(expect_errors=expect_errors)

    def preflight(self, expect_errors=False):
        self.do_and_check('preflight', expect_errors)

    def deploy(self, expect_errors=False):
        self.do_and_check('deploy', expect_errors)

    def postflight(self, expect_errors=False):
        self.do_and_check('postflight', expect_errors)

    def do_and_check(self, action, expect_errors):
        """Args:
            action (str): one of 'preflight', 'deploy', 'postflight'
        """
        self.start_action(action)
        self.wait_for_check_action(
            action=action, expect_errors=expect_errors,
            wait=30000, stop_max_delay=900*1000)

    def wait_for_check_action(self, action, wait, stop_max_delay, expect_errors):
        """Retries method against API until returned data shows that all hosts
        have finished.

        Args:
            action (str): choies are 'preflight', 'deploy', 'postflight'
            wait (int): how many milliseconds to wait between tries
            stop_max_delay (int): total duration (in milliseconds) to retry for
            expect_errors (boolean): raises error if result is not as expected

        Raises:
            AssertionError: checks 'host_status' and raises error...
                -if expect_errors is False and not all status=='success'
                -if expect_errors is True and all status=='success'
        """
        @retry(wait_fixed=wait, stop_max_delay=stop_max_delay)
        def wait_for_finish():
            # Only return if output is not empty and all hosts are not running
            output = self.check_action(action)
            assert output != {}
            host_data = output['hosts']
            finished_run = all(map(lambda host: host['host_status'] not in ['running', 'unstarted'],
                                   host_data.values()))
            assert finished_run, 'Action timed out! Last output: {}'.format(output)
            return host_data

        host_data = wait_for_finish()
        success = True
        for host in host_data.keys():
            if host_data[host]['host_status'] != 'success':
                success = False
                print("Failures detected in {}: {}".format(action, host_data[host]))
        if expect_errors:
            assert not success, "Results were successful, but errors were expected in {}".format(action)
        else:
            assert success, "Results for {} included failures, when all should have succeeded".format(action)

    def start_action(self, action):
        """Args:
            action (str): one of 'preflight', 'deploy', 'postflight'
        """
        return requests.post(self.url + '/api/v1/action/{}'.format(action))

    def check_action(self, action):
        """Args:
            action (str): one of 'preflight', 'deploy', 'postflight', 'success'
        """
        return requests.get(self.url + '/api/v1/action/{}'.format(action)).json()


class DcosCliInstaller(AbstractDcosInstaller):
    def run_cli_cmd(self, mode, expect_errors=False):
        """Runs commands through the CLI
        NOTE: We use `bash` as a wrapper here to make it so dcos_generate_config.sh
        doesn't have to be executable

        Args:
            mode (str): single flag to be handed to CLI
            expect_errors: raise error if result is unexpected

        Raises:
            AssertionError: if return_code is...
                -zero and expect_errors is True
                -nonzero and expect_errors is False
        """
        cmd = ['bash', self.installer_path, mode]
        if expect_errors:
            try:
                output = self.ssh(cmd)
                err_msg = "{} succeeded when it should have failed".format(cmd)
                print(output)
                raise AssertionError(err_msg)
            except CalledProcessError:
                # expected behavior
                pass
        else:
            print(self.ssh(cmd))

    def genconf(
            self, master_list, agent_list, public_agent_list, ssh_user, ssh_key,
            ip_detect_script, zk_host=None, expect_errors=False, add_config_path=None):
        """Runs configuration generation.

        Args:
            master_list: list of IPv4 addresses to be used as masters
            agent_list: list of IPv4 addresses to be used as agents
            public_agent_list: list of IPv$ addresses to be used as public agents
            ip_detect_script (str): complete contents of IP-detect script
            ssh_user (str): name of SSH user that has access to targets
            ssh_key (str): complete public SSH key for ssh_user. Must already
                be installed on tagets as authorized_key
            zk_host (optional): if provided, zk is used for exhibitor backend
            expect_errors (optional): raises error if result is unexpected
            add_config_path (optional): string pointing to a file with additional
                config parameters to be merged or used as overide

        Raises:
            AssertionError: "error" present in returned json keys when error
                was not expected or vice versa
        """
        test_config = {
            'cluster_name': 'SSH Installed DC/OS',
            'bootstrap_url': 'file:///opt/dcos_install_tmp',
            'dns_search': 'mesos',
            'master_discovery': 'static',
            'master_list': master_list,
            'ssh_user': ssh_user,
            'agent_list': agent_list,
            'public_agent_list': public_agent_list,
            'process_timeout': 900}
        if zk_host:
            test_config['exhibitor_storage_backend'] = 'zookeeper'
            test_config['exhibitor_zk_hosts'] = zk_host
            test_config['exhibitor_zk_path'] = '/exhibitor'
        else:
            test_config['exhibitor_storage_backend'] = 'static'
        if add_config_path:
            with open(add_config_path, 'r'):
                add_config = yaml.load(add_config_path)
            test_config.update(add_config)
        with open('config.yaml', 'w') as config_fh:
            config_fh.write(yaml.dump(test_config))
        with open('ip-detect', 'w') as ip_detect_fh:
            ip_detect_fh.write(ip_detect_script)
        with open('ssh_key', 'w') as key_fh:
            key_fh.write(ssh_key)
        remote_dir = os.path.dirname(self.installer_path)
        self.ssh(['mkdir', '-p', os.path.join(remote_dir, 'genconf')])
        self.scp('config.yaml', os.path.join(remote_dir, 'genconf/config.yaml'))
        self.scp('ip-detect', os.path.join(remote_dir, 'genconf/ip-detect'))
        self.scp('ssh_key', os.path.join(remote_dir, 'genconf/ssh_key'))
        self.ssh(['chmod', '600', os.path.join(remote_dir, 'genconf/ssh_key')])
        self.run_cli_cmd('--genconf', expect_errors=expect_errors)

    def preflight(self, expect_errors=False):
        self.run_cli_cmd('--preflight', expect_errors=expect_errors)

    def install_prereqs(self, expect_errors=False):
        self.run_cli_cmd('--install-prereqs', expect_errors=expect_errors)
        self.preflight()

    def deploy(self, expect_errors=False):
        self.run_cli_cmd('--deploy', expect_errors=expect_errors)

    def postflight(self, expect_errors=False):
        self.run_cli_cmd('--postflight', expect_errors=expect_errors)


class Host:
    def __init__(self, private_ip, public_ip):
        self.private_ip = private_ip
        self.public_ip = public_ip


def do_install(installer_url,
               ssh_user,
               ssh_key_path,
               test_host,
               master_list,
               agent_list,
               public_agent_list,
               method,
               install_prereqs,
               do_setup,
               remote_dir,
               add_config_path,
               stop_after_prereqs,
               run_test,
               aws_region,
               dcos_variant,
               provider,
               ci_flags,
               aws_access_key_id,
               aws_secret_access_key,
               add_env):
    log.info('Test host public/private IP: ' + test_host.public_ip + '/' + test_host.private_ip)

    if method == 'web_api':
        installer = DcosApiInstaller(not install_prereqs)
    else:
        assert method == 'ssh'
        installer = DcosCliInstaller()

    with closing(SSHTunnel(ssh_user, ssh_key_path, test_host.public_ip)) as test_host_tunnel:
        log.info('Setting up installer on test host')

        installer.setup_remote(
            tunnel=test_host_tunnel,
            installer_path=remote_dir + '/dcos_generate_config.sh',
            download_url=installer_url)
        if do_setup:
            # only do on setup so you can rerun this test against a living installer
            log.info('Verifying installer password hashing')
            test_pass = 'testpassword'
            hash_passwd = installer.get_hashed_password(test_pass)
            assert passlib.hash.sha512_crypt.verify(test_pass, hash_passwd), 'Hash does not match password'

        if method == 'web_api':
            installer.start_web_server()

        # TODO(cmaloney): Make a option which implicitly does this inside gen.
        ip_detect_script = pkg_resources.resource_string("gen", "ip-detect/aws.sh")
        with open('ssh_key', 'r') as key_fh:
            ssh_key = key_fh.read()
        # Using static exhibitor is the only option in the GUI installer
        if method == 'web_api':
            log.info('Installer API is selected, so configure for static backend')
            zk_host = None  # causes genconf to use static exhibitor backend
        else:
            log.info('Installer CLI is selected, so configure for ZK backend')
            zk_host = test_host.private_ip + ':2181'
            zk_cmd = [
                'sudo', 'docker', 'run', '-d', '-p', '2181:2181', '-p',
                '2888:2888', '-p', '3888:3888', 'jplock/zookeeper']
            test_host_tunnel.remote_cmd(zk_cmd)

        log.info("Configuring install...")
        installer.genconf(
            zk_host=zk_host.private_ip,
            master_list=[host.private_ip for host in master_list],
            agent_list=agent_list,
            public_agent_list=[host.private_ip for host in master_list],
            ip_detect_script=ip_detect_script,
            ssh_user=ssh_user,
            ssh_key=ssh_key,
            add_config_path=add_config_path)

        log.info("Running Preflight...")
        if install_prereqs:
            # Runs preflight in --web or --install-prereqs for CLI
            # This may take up 15 minutes...
            installer.install_prereqs()
            if stop_after_prereqs:
                return True
        else:
            # Will not fix errors detected in preflight
            installer.preflight()

        log.info("Running Deploy...")
        installer.deploy()

        log.info("Running Postflight")
        installer.postflight()

        if run_test:
            # Runs dcos-image/integration_test.py inside the cluster
            test_util.test_runner.prepare_test_registry(
                tunnel=test_host_tunnel,
                test_dir=remote_dir)
            test_util.test_runner.integration_test(
                tunnel=test_host_tunnel,
                test_dir=remote_dir,
                region=aws_region,
                dcos_dns=master_list[0],
                master_list=master_list,
                agent_list=agent_list,
                public_agent_list=public_agent_list,
                # Setting dns_search: mesos not currently supported in API
                test_dns_search=method != 'web_api',
                provider=provider,
                ci_flags=ci_flags,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                add_env=add_env)
        log.info("Test successsful!")
