"""Python API for interacting with installer API
"""
import abc
import json
import os
import subprocess

import requests
import yaml
from retrying import retry


class AbstractDcosInstaller(metaclass=abc.ABCMeta):

    def __init__(self):
        self.offline_mode = False

    def setup_remote(self, host, ssh_user, ssh_key_path, installer_path, download_url):
        # Refresh ssh info
        self.url = "http://{}:9000".format(host)
        self.installer_path = installer_path
        self.host = host
        ssh_opts = [
                '-i', ssh_key_path,
                '-oConnectTimeout=10',
                '-oStrictHostKeyChecking=no',
                '-oUserKnownHostsFile=/dev/null',
                '-oBatchMode=yes',
                '-oPasswordAuthentication=no']

        def ssh(cmd):
            assert isinstance(cmd, list)
            return ['/usr/bin/ssh']+ssh_opts+['{}@{}'.format(ssh_user, host)]+cmd

        def scp(src, dst):
            return ['/usr/bin/scp']+ssh_opts+[src, '{}@{}:{}'.format(ssh_user, host, dst)]

        self.ssh = ssh
        self.scp = scp
        if download_url:
            dir_name = os.path.dirname(self.installer_path)
            if len(dir_name) > 0:
                subprocess.check_call(self.ssh(['mkdir', '-p', dir_name]))

            @retry
            def curl_download():
                # If it takes more than 5 minutes, it probably got hung
                subprocess.check_call(self.ssh(['curl', '-s', '-m', '300', download_url, '>', self.installer_path]))

            curl_download()

    def get_hashed_password(self, password):
        p = subprocess.Popen(
                self.ssh(["bash", self.installer_path, "--hash-password", password]),
                stdout=subprocess.PIPE)
        # there is a newline after the hash, so second to last split is hash
        passwd_hash = p.communicate()[0].decode('ascii').split('\n')[-2]
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

    def start_web_server(self):
        cmd = ['DCOS_INSTALLER_DAEMONIZE=true', 'bash', self.installer_path, '--web']
        if self.offline_mode:
            cmd.append('--offline')
        subprocess.check_call(self.ssh(cmd))

        @retry(wait_fixed=1000, stop_max_delay=10000)
        def wait_for_up():
            assert requests.get(self.url).status_code == 200
            print("Webserver started")

        wait_for_up()

    def genconf(
            self, master_list, agent_list, ssh_user, ssh_key,
            ip_detect_script, zk_host=None,
            expect_errors=False):
        """Runs configuration generation.

        Args:
            master_list: list of IPv4 addresses to be used as masters
            agent_list: list of IPv4 addresses to be used as agents
            ip_detect_script (str): complete contents of IP-detect script
            ssh_user (str): name of SSH user that has access to targets
            ssh_key (str): complete public SSH key for ssh_user. Must already
                be installed on tagets as authorized_key
            zk_host (optional): if provided, zk is used for exhibitor backend
            expect_errors (optional): raises error if result is unexpected

        Raises:
            AssertionError: "error" present in returned json keys when error
                was not expected or vice versa
        """
        headers = {'content-type': 'application/json'}
        payload = {
            'master_list': master_list,
            'agent_list': agent_list,
            'ssh_user': ssh_user,
            'ssh_key': ssh_key,
            'ip_detect_script': ip_detect_script}
        if zk_host:
            payload['exhibitor_zk_hosts'] = zk_host
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
            finished_run = all(map(lambda host: host['host_status'] != 'running', host_data.values()))
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
        p = subprocess.Popen(self.ssh(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = p.communicate()[1].decode()
        if expect_errors:
            err_msg = "{} exited with error code {} (success), but expected an error.\nOutput: {}"
            assert p.returncode != 0, err_msg.format(mode, p.returncode, out)
        else:
            err_msg = "{} exited with error code {}.\nOutput: {}"
            assert p.returncode == 0, err_msg.format(mode, p.returncode, out)

    def genconf(
            self, master_list, agent_list, ssh_user, ssh_key,
            ip_detect_script, zk_host=None, expect_errors=False):
        """Runs configuration generation.

        Args:
            master_list: list of IPv4 addresses to be used as masters
            agent_list: list of IPv4 addresses to be used as agents
            ip_detect_script (str): complete contents of IP-detect script
            ssh_user (str): name of SSH user that has access to targets
            ssh_key (str): complete public SSH key for ssh_user. Must already
                be installed on tagets as authorized_key
            zk_host (optional): if provided, zk is used for exhibitor backend
            expect_errors (optional): raises error if result is unexpected

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
            'process_timeout': 900}
        if zk_host:
            test_config['exhibitor_storage_backend'] = 'zookeeper'
            test_config['exhibitor_zk_hosts'] = zk_host
            test_config['exhibitor_zk_path'] = '/exhibitor'
        else:
            test_config['exhibitor_storage_backend'] = 'static'
        with open('config.yaml', 'w') as config_fh:
            config_fh.write(yaml.dump(test_config))
        with open('ip-detect', 'w') as ip_detect_fh:
            ip_detect_fh.write(ip_detect_script)
        with open('ssh_key', 'w') as key_fh:
            key_fh.write(ssh_key)
        remote_dir = os.path.dirname(self.installer_path)
        subprocess.check_call(self.ssh(['mkdir', '-p', os.path.join(remote_dir, 'genconf')]))
        subprocess.check_call(self.scp('config.yaml', os.path.join(remote_dir, 'genconf/config.yaml')))
        subprocess.check_call(self.scp('ip-detect', os.path.join(remote_dir, 'genconf/ip-detect')))
        subprocess.check_call(self.scp('ssh_key', os.path.join(remote_dir, 'genconf/ssh_key')))
        subprocess.check_call(self.ssh(['chmod', '600', os.path.join(remote_dir, 'genconf/ssh_key')]))
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
