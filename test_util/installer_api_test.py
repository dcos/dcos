"""Python API for interacting with installer API
"""
import abc
import json
import os
from subprocess import CalledProcessError
from typing import Optional

import pkg_resources
import requests
import yaml
from retrying import retry

from pkgpanda.util import load_yaml
from ssh.tunnel import Tunnelled

MAX_STAGE_TIME = int(os.getenv('INSTALLER_API_MAX_STAGE_TIME', '900'))


class AbstractDcosInstaller(metaclass=abc.ABCMeta):

    def __init__(self):
        self.offline_mode = False

    def setup_remote(
            self, tunnel: Optional[Tunnelled], installer_path, download_url):
        """Creates a light, system-based ssh handler
        Args:
            tunnel: Tunneled instance to avoid recreating SSH connections.
                If set to None, ssh_user, host, and ssh_key_path must be
                set and one-off connections will be made
            installer_path: (str) path on host to download installer to
            download_url: (str) URL that installer can be pulled from
        """
        self.installer_path = installer_path
        self.tunnel = tunnel
        self.url = "http://{}:9000".format(tunnel.host)

        @retry(wait_fixed=3000, stop_max_delay=300 * 1000)
        def download_dcos():
            """Response status 403 is fatal for curl's retry. Additionally, S3 buckets
            have been returning 403 for valid uploads for 10-15 minutes after CI finished build
            Therefore, give a five minute buffer to help stabilize CI
            """
            self.tunnel.remote_cmd(['curl', '-fLsSv', '--retry', '20', '-Y', '100000', '-y', '60',
                                    '--create-dirs', '-o', self.installer_path, download_url])

        if download_url:
            download_dcos()

    def get_hashed_password(self, password):
        p = self.tunnel.remote_cmd(["bash", self.installer_path, "--hash-password", password])
        # password hash is last line output but output ends with newline
        passwd_hash = p.decode('utf-8').split('\n')[-2]
        return passwd_hash

    @staticmethod
    def ip_detect_script(preset_name):
        try:
            return pkg_resources.resource_string('gen', 'ip-detect/{}.sh'.format(preset_name)).decode('utf-8')
        except OSError as exc:
            raise Exception('Failed to read ip-detect script preset {}: {}'.format(preset_name, exc)) from exc

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

    def start_web_server(self):
        cmd = ['DCOS_INSTALLER_DAEMONIZE=true', 'bash', self.installer_path, '--web']
        if self.offline_mode:
            cmd.append('--offline')
        self.tunnel.remote_cmd(cmd)

        @retry(wait_fixed=1000, stop_max_delay=10000)
        def wait_for_up():
            response = requests.get(self.url)
            assert response.status_code == 200, "{} {}".format(response.status_code, response.content)
            print("Webserver started")

        wait_for_up()

    def genconf(
            self, master_list, agent_list, public_agent_list, ssh_user, ssh_key,
            ip_detect, platform=None, rexray_config=None, rexray_config_preset=None,
            zk_host=None, expect_errors=False, add_config_path=None):
        """Runs configuration generation.

        Args:
            master_list: list of IPv4 addresses to be used as masters
            agent_list: list of IPv4 addresses to be used as agents
            public_agent_list: list of IPv4 addresses to be used as public agents
            ssh_user (str): name of SSH user that has access to targets
            ssh_key (str): complete public SSH key for ssh_user. Must already
                be installed on tagets as authorized_key
            ip_detect (str):  name of preset IP-detect script
            platform (str): name of the infrastructure platform
            rexray_config: complete contents of REX-Ray config file. Must be a
                JSON-serializable object.
            rexray_config_preset (str): name of preset REX-Ray config
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
            'ip_detect_script': self.ip_detect_script(ip_detect)}
        if platform:
            payload['platform'] = platform
        if rexray_config:
            payload['rexray_config'] = rexray_config
        if rexray_config_preset:
            payload['rexray_config_preset'] = rexray_config_preset
        if zk_host:
            payload['exhibitor_zk_hosts'] = zk_host
        if add_config_path:
            add_config = load_yaml(add_config_path)
            payload.update(add_config)
        response = requests.post(self.url + '/api/v1/configure', headers=headers, data=json.dumps(payload))
        assert response.status_code == 200, "{} {}".format(response.status_code, response.content)
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
            wait=30000, stop_max_delay=MAX_STAGE_TIME * 1000)

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
                output = self.tunnel.remote_cmd(cmd, timeout=MAX_STAGE_TIME)
                err_msg = "{} succeeded when it should have failed".format(cmd)
                print(output)
                raise AssertionError(err_msg)
            except CalledProcessError:
                # expected behavior
                pass
        else:
            output = self.tunnel.remote_cmd(cmd, timeout=MAX_STAGE_TIME)
            print(output)
            return output

    def genconf(
            self, master_list, agent_list, public_agent_list, ssh_user, ssh_key,
            ip_detect, platform=None, rexray_config=None, rexray_config_preset=None,
            zk_host=None, expect_errors=False, add_config_path=None,
            bootstrap_url='file:///opt/dcos_install_tmp'):
        """Runs configuration generation.

        Args:
            master_list: list of IPv4 addresses to be used as masters
            agent_list: list of IPv4 addresses to be used as agents
            public_agent_list: list of IPv$ addresses to be used as public agents
            ssh_user (str): name of SSH user that has access to targets
            ssh_key (str): complete public SSH key for ssh_user. Must already
                be installed on tagets as authorized_key
            ip_detect (str):  name of preset IP-detect script
            platform (str): name of the infrastructure platform
            rexray_config: complete contents of REX-Ray config file. Must be a
                JSON-serializable object.
            rexray_config_preset (str): name of preset REX-Ray config
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
            'bootstrap_url': bootstrap_url,
            'dns_search': 'mesos',
            'master_discovery': 'static',
            'master_list': master_list,
            'ssh_user': ssh_user,
            'agent_list': agent_list,
            'public_agent_list': public_agent_list,
            'process_timeout': MAX_STAGE_TIME}
        if platform:
            test_config['platform'] = platform
        if rexray_config:
            test_config['rexray_config'] = rexray_config
        if rexray_config_preset:
            test_config['rexray_config_preset'] = rexray_config_preset
        if zk_host:
            test_config['exhibitor_storage_backend'] = 'zookeeper'
            test_config['exhibitor_zk_hosts'] = zk_host
            test_config['exhibitor_zk_path'] = '/exhibitor'
        else:
            test_config['exhibitor_storage_backend'] = 'static'
        if add_config_path:
            add_config = load_yaml(add_config_path)
            test_config.update(add_config)
        with open('config.yaml', 'w') as config_fh:
            config_fh.write(yaml.dump(test_config))
        with open('ip-detect', 'w') as ip_detect_fh:
            ip_detect_fh.write(self.ip_detect_script(ip_detect))
        with open('ssh_key', 'w') as key_fh:
            key_fh.write(ssh_key)
        remote_dir = os.path.dirname(self.installer_path)
        self.tunnel.remote_cmd(['mkdir', '-p', os.path.join(remote_dir, 'genconf')])
        self.tunnel.write_to_remote('config.yaml', os.path.join(remote_dir, 'genconf/config.yaml'))
        self.tunnel.write_to_remote('ip-detect', os.path.join(remote_dir, 'genconf/ip-detect'))
        self.tunnel.write_to_remote('ssh_key', os.path.join(remote_dir, 'genconf/ssh_key'))
        self.tunnel.remote_cmd(['chmod', '600', os.path.join(remote_dir, 'genconf/ssh_key')])
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

    def generate_node_upgrade_script(self, version, expect_errors=False):
        # tunnel run_cmd calls check_output which returns the output hence returning this
        return self.run_cli_cmd("--generate-node-upgrade-script " + version, expect_errors=expect_errors)
