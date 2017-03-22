#!/usr/bin/env python3
"""Integration test for onprem DC/OS upgraded from latest stable.

The following environment variables control test procedure:

MASTERS: integer (default=3)
    The number of masters to create from a newly created VPC.

AGENTS: integer (default=2)
    The number of agents to create from a newly created VPC.

PUBLIC_AGENTS: integer (default=1)
    The number of public agents to create from a newly created VPC.

INSTALLER_URL: Installer URL for the DC/OS release under test.

STABLE_INSTALLER_URL: Installer URL for the latest stable DC/OS release.

CI_FLAGS: string (default=None)
    If provided, this string will be passed directly to py.test as in:
    py.test -vv CI_FLAGS integration_test.py

DCOS_PYTEST_CMD: string(default='py.test -rs -vv ' + os.getenv('CI_FLAGS', ''))
    The complete py.test command used to run integration tests. If provided,
    CI_FLAGS is ignored.

CONFIG_YAML_OVERRIDE_INSTALL: file path(default=None)
    If provided the file specified will be loaded as a config.yaml and all properties specified
    in the file will override any previously defined values.
    This value will be used for the initial install of the cluster.

CONFIG_YAML_OVERRIDE_UPGRADE: file path(default=None)
    If provided the file specified will be loaded as a config.yaml and all properties specified
    in the file will override any previously defined values.
    This value will be used when upgrading the cluster.

"""
import logging
import os
import pprint
import sys
import traceback
import uuid
from typing import Callable, List

import retrying
from teamcity.messages import TeamcityServiceMessages

import test_util.aws
import test_util.cluster
from pkgpanda.util import logger, write_string
from test_util.dcos_api_session import DcosApiSession, DcosUser
from test_util.helpers import CI_CREDENTIALS, marathon_app_id_to_mesos_dns_subdomain, random_id


logging.basicConfig(format='[%(asctime)s|%(name)s|%(levelname)s]: %(message)s', level=logging.DEBUG)


TEST_APP_NAME_FMT = 'upgrade-{}'


def create_marathon_viplisten_app():
    return {
        "id": '/' + TEST_APP_NAME_FMT.format('viplisten-' + uuid.uuid4().hex),
        "cmd": '/usr/bin/nc -l -p $PORT0',
        "cpus": 0.1,
        "mem": 32,
        "instances": 1,
        "container": {
            "type": "MESOS",
            "docker": {
              "image": "alpine:3.5"
            }
        },
        'portDefinitions': [{
            'labels': {
                'VIP_0': '/viplisten:5000'
            }
        }],
        "healthChecks": [{
            "protocol": "COMMAND",
            "command": {
                "value": "/usr/bin/nslookup viplisten.marathon.l4lb.thisdcos.directory && pgrep -x /usr/bin/nc"
            },
            "gracePeriodSeconds": 300,
            "intervalSeconds": 60,
            "timeoutSeconds": 20,
            "maxConsecutiveFailures": 3
        }]
    }


def create_marathon_viptalk_app():
    return {
        "id": '/' + TEST_APP_NAME_FMT.format('viptalk-' + uuid.uuid4().hex),
        "cmd": "/usr/bin/nc viplisten.marathon.l4lb.thisdcos.directory 5000 < /dev/zero",
        "cpus": 0.1,
        "mem": 32,
        "instances": 1,
        "container": {
            "type": "MESOS",
            "docker": {
              "image": "alpine:3.5"
            }
        },
        "healthChecks": [{
            "protocol": "COMMAND",
            "command": {
                "value": "pgrep -x /usr/bin/nc && sleep 5 && pgrep -x /usr/bin/nc"
            },
            "gracePeriodSeconds": 300,
            "intervalSeconds": 60,
            "timeoutSeconds": 20,
            "maxConsecutiveFailures": 3
        }]
    }


def create_marathon_healthcheck_app(app_id: str) -> dict:
    # HTTP healthcheck app to make sure tasks are reachable during the upgrade.
    # If a task fails its healthcheck, Marathon will terminate it and we'll
    # notice it was killed when we check tasks on exit.
    return {
        "id": '/' + app_id,
        "cmd": "python3 -m http.server 8080",
        "cpus": 0.5,
        "mem": 32.0,
        "instances": 1,
        "container": {
            "type": "DOCKER",
            "docker": {
                "image": "python:3",
                "network": "BRIDGE",
                "portMappings": [
                    {"containerPort": 8080, "hostPort": 0}
                ]
            }
        },
        "healthChecks": [
            {
                "protocol": "HTTP",
                "path": "/",
                "portIndex": 0,
                "gracePeriodSeconds": 5,
                "intervalSeconds": 1,
                "timeoutSeconds": 5,
                "maxConsecutiveFailures": 1
            }
        ],
    }


def create_marathon_dns_app(app_id: str, healthcheck_app_id: str) -> dict:
    # DNS resolution app to make sure DNS is available during the upgrade.
    # Periodically resolves the healthcheck app's domain name and logs whether
    # it succeeded to a file in the Mesos sandbox.
    return {
        "id": '/' + app_id,
        "cmd": """
while true
do
    printf "%s " $(date --utc -Iseconds) >> $MESOS_SANDBOX/$DNS_LOG_FILENAME
    if host -W $TIMEOUT_SECONDS $RESOLVE_NAME
    then
        echo SUCCESS >> $MESOS_SANDBOX/$DNS_LOG_FILENAME
    else
        echo FAILURE >> $MESOS_SANDBOX/$DNS_LOG_FILENAME
    fi
    sleep $INTERVAL_SECONDS
done
""",
        "env": {
            'RESOLVE_NAME': marathon_app_id_to_mesos_dns_subdomain(healthcheck_app_id) + '.marathon.mesos',
            'DNS_LOG_FILENAME': 'dns_resolve_log.txt',
            'INTERVAL_SECONDS': '1',
            'TIMEOUT_SECONDS': '1',
        },
        "cpus": 0.5,
        "mem": 32.0,
        "instances": 1,
        "container": {
            "type": "DOCKER",
            "docker": {
                "image": "branden/bind-utils",
                "network": "BRIDGE",
            }
        },
        "dependencies": [healthcheck_app_id],
    }


class VpcClusterUpgradeTestDcosApiSessionFactory:
    def apply(self, dcos_url: str, masters: List[str], public_masters: List[str], slaves: List[str],
              public_slaves: List[str], default_os_user: str) -> DcosApiSession:
        pass


class VpcClusterUpgradeTest:
    log = logging.getLogger(__name__)

    def __init__(self,
                 num_masters: int, num_agents: int, num_public_agents: int,
                 stable_installer_url: str, installer_url: str,
                 aws_region: str, aws_access_key_id: str, aws_secret_access_key: str,
                 default_os_user: str,
                 config_yaml_override_install: str, config_yaml_override_upgrade: str,
                 dcos_api_session_factory_install: VpcClusterUpgradeTestDcosApiSessionFactory,
                 dcos_api_session_factory_upgrade: VpcClusterUpgradeTestDcosApiSessionFactory):

        self.dcos_api_session_factory_install = dcos_api_session_factory_install
        self.dcos_api_session_factory_upgrade = dcos_api_session_factory_upgrade
        self.num_masters = num_masters
        self.num_agents = num_agents
        self.num_public_agents = num_public_agents
        self.stable_installer_url = stable_installer_url
        self.installer_url = installer_url
        self.aws_region = aws_region
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.default_os_user = default_os_user
        self.config_yaml_override_install = config_yaml_override_install
        self.config_yaml_override_upgrade = config_yaml_override_upgrade

        self.teamcity_msg = TeamcityServiceMessages()

        # the two following properties are set when running setup_cluster_workload, here we default them to empty
        # values.
        self.test_app_ids = []
        self.tasks_start = []

    @staticmethod
    def app_task_ids(dcos_api, app_id):
        """Return a list of Mesos task IDs for app_id's running tasks."""
        assert app_id.startswith('/')
        response = dcos_api.marathon.get('/v2/apps' + app_id + '/tasks')
        response.raise_for_status()
        tasks = response.json()['tasks']
        return [task['id'] for task in tasks]

    @staticmethod
    def get_master_task_state(dcos_api, task_id):
        """Returns the JSON blob associated with the task from /master/state."""
        response = dcos_api.get('/mesos/master/state')
        response.raise_for_status()
        master_state = response.json()

        for framework in master_state['frameworks']:
            for task in framework['tasks']:
                if task_id in task['id']:
                    return task

    def parse_dns_log(self, dns_log_content):
        """Return a list of (timestamp, status) tuples from dns_log_content."""
        dns_log = [line.strip().split(' ') for line in dns_log_content.strip().split('\n')]
        if any(len(entry) != 2 or entry[1] not in ['SUCCESS', 'FAILURE'] for entry in dns_log):
            message = 'Malformed DNS log.'
            self.log.debug(message + ' DNS log content:\n' + dns_log_content)
            raise Exception(message)
        return dns_log

    def log_test(self, test_name: str, call: Callable[[], None]) -> None:
        try:
            self.teamcity_msg.testStarted(test_name)
            call()
        except Exception:
            # we want this except to be broad so that we can keep any Exception from taking
            # everything with it and not asserting the other tests
            self.teamcity_msg.testFailed(test_name, details=traceback.format_exc())
        finally:
            self.teamcity_msg.testFinished(test_name)

    @staticmethod
    @retrying.retry(
        wait_fixed=(1 * 1000),
        stop_max_delay=(120 * 1000),
        retry_on_result=lambda x: not x)
    def wait_for_dns(dcos_api, hostname):
        """Return True if Mesos-DNS has at least one entry for hostname."""
        hosts = dcos_api.get('/mesos_dns/v1/hosts/' + hostname).json()
        return any(h['host'] != '' and h['ip'] != '' for h in hosts)

    def setup_cluster_workload(self, dcos_api: DcosApiSession, healthcheck_app: dict, dns_app: dict,
                               viplisten_app: dict, viptalk_app: dict):
        # Deploy test apps.
        # TODO(branden): We ought to be able to deploy these apps concurrently. See
        # https://mesosphere.atlassian.net/browse/DCOS-13360.
        with logger.scope("deploy apps"):

            dcos_api.marathon.deploy_app(viplisten_app)
            dcos_api.marathon.ensure_deployments_complete()
            dcos_api.marathon.deploy_app(viptalk_app)
            dcos_api.marathon.ensure_deployments_complete()

            dcos_api.marathon.deploy_app(healthcheck_app)
            dcos_api.marathon.ensure_deployments_complete()
            # This is a hack to make sure we don't deploy dns_app before the name it's
            # trying to resolve is available.
            self.wait_for_dns(dcos_api, dns_app['env']['RESOLVE_NAME'])
            dcos_api.marathon.deploy_app(dns_app, check_health=False)
            dcos_api.marathon.ensure_deployments_complete()

            test_apps = [healthcheck_app, dns_app, viplisten_app, viptalk_app]
            self.test_app_ids = [app['id'] for app in test_apps]

            self.tasks_start = {app_id: sorted(self.app_task_ids(dcos_api, app_id)) for app_id in self.test_app_ids}
            self.log.debug('Test app tasks at start:\n' + pprint.pformat(self.tasks_start))

            for app in test_apps:
                assert app['instances'] == len(self.tasks_start[app['id']])

            # Save the master's state of the task to compare with
            # the master's view after the upgrade.
            # See this issue for why we check for a difference:
            # https://issues.apache.org/jira/browse/MESOS-1718
            self.task_state_start = self.get_master_task_state(dcos_api, self.tasks_start[self.test_app_ids[0]][0])

    def verify_apps_state(self, dcos_api: DcosApiSession, dns_app: dict):
        with logger.scope("verify apps state"):

            # nested methods here so we can "close" over external state

            def marathon_app_tasks_survive_upgrade():
                # Verify that the tasks we started are still running.
                tasks_end = {app_id: sorted(self.app_task_ids(dcos_api, app_id)) for app_id in self.test_app_ids}
                self.log.debug('Test app tasks at end:\n' + pprint.pformat(tasks_end))
                if not self.tasks_start == tasks_end:
                    self.teamcity_msg.testFailed(
                        "test_upgrade_vpc.marathon_app_tasks_survive_upgrade",
                        details="expected: {}\nactual:   {}".format(self.tasks_start, tasks_end))

            def test_mesos_task_state_remains_consistent():
                # Verify that the "state" of the task does not change.
                task_state_end = self.get_master_task_state(dcos_api, self.tasks_start[self.test_app_ids[0]][0])
                if not self.task_state_start == task_state_end:
                    self.teamcity_msg.testFailed(
                        "test_upgrade_vpc.test_mesos_task_state_remains_consistent",
                        details="expected: {}\nactual:   {}".format(self.task_state_start, task_state_end))

            def test_app_dns_survive_upgrade():
                # Verify DNS didn't fail.
                marathon_framework_id = dcos_api.marathon.get('/v2/info').json()['frameworkId']
                dns_app_task = dcos_api.marathon.get('/v2/apps' + dns_app['id'] + '/tasks').json()['tasks'][0]
                dns_log = self.parse_dns_log(dcos_api.mesos_sandbox_file(
                    dns_app_task['slaveId'],
                    marathon_framework_id,
                    dns_app_task['id'],
                    dns_app['env']['DNS_LOG_FILENAME'],
                ))
                dns_failure_times = [entry[0] for entry in dns_log if entry[1] != 'SUCCESS']
                if len(dns_failure_times) > 0:
                    message = 'Failed to resolve Marathon app hostname {} at least once.'.format(
                        dns_app['env']['RESOLVE_NAME'])
                    err_msg = message + ' Hostname failed to resolve at these times:\n' + '\n'.join(dns_failure_times)
                    self.log.debug(err_msg)
                    self.teamcity_msg.testFailed("test_upgrade_vpc.test_app_dns_survive_upgrade", details=err_msg)

            self.log_test("test_upgrade_vpc.marathon_app_tasks_survive_upgrade", marathon_app_tasks_survive_upgrade)
            self.log_test(
                "test_upgrade_vpc.test_mesos_task_state_remains_consistent",
                test_mesos_task_state_remains_consistent
            )
            self.log_test("test_upgrade_vpc.test_app_dns_survive_upgrade", test_app_dns_survive_upgrade)

    def run_test(self) -> int:
        stack_suffix = os.getenv("CF_STACK_NAME_SUFFIX", "open-upgrade")
        stack_name = "dcos-ci-test-{stack_suffix}-{random_id}".format(
            stack_suffix=stack_suffix, random_id=random_id(10))

        test_id = uuid.uuid4().hex
        healthcheck_app_id = TEST_APP_NAME_FMT.format('healthcheck-' + test_id)
        dns_app_id = TEST_APP_NAME_FMT.format('dns-' + test_id)

        with logger.scope("create vpc cf stack '{}'".format(stack_name)):
            bw = test_util.aws.BotoWrapper(
                region=self.aws_region,
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key)
            ssh_key = bw.create_key_pair(stack_name)
            write_string('ssh_key', ssh_key)
            vpc, ssh_info = test_util.aws.VpcCfStack.create(
                stack_name=stack_name,
                instance_type='m4.xlarge',
                instance_os='cent-os-7-dcos-prereqs',
                # An instance for each cluster node plus the bootstrap.
                instance_count=(self.num_masters + self.num_agents + self.num_public_agents + 1),
                admin_location='0.0.0.0/0',
                key_pair_name=stack_name,
                boto_wrapper=bw
            )
            vpc.wait_for_complete()

        cluster = test_util.cluster.Cluster.from_vpc(
            vpc,
            ssh_info,
            ssh_key=ssh_key,
            num_masters=self.num_masters,
            num_agents=self.num_agents,
            num_public_agents=self.num_public_agents,
        )

        with logger.scope("install dcos"):
            # Use the CLI installer to set exhibitor_storage_backend = zookeeper.
            # Don't install prereqs since stable breaks Docker 1.13. See
            # https://jira.mesosphere.com/browse/DCOS_OSS-743.
            test_util.cluster.install_dcos(cluster, self.stable_installer_url, api=False, install_prereqs=False,
                                           add_config_path=self.config_yaml_override_install)

            master_list = [h.private_ip for h in cluster.masters]

            dcos_api_install = self.dcos_api_session_factory_install.apply(
                'http://{ip}'.format(ip=cluster.masters[0].public_ip),
                master_list,
                master_list,
                [h.private_ip for h in cluster.agents],
                [h.private_ip for h in cluster.public_agents],
                self.default_os_user)

            dcos_api_install.wait_for_dcos()

        installed_version = dcos_api_install.get_version()
        healthcheck_app = create_marathon_healthcheck_app(healthcheck_app_id)
        dns_app = create_marathon_dns_app(dns_app_id, healthcheck_app_id)
        viplisten_app = create_marathon_viplisten_app()
        viptalk_app = create_marathon_viptalk_app()

        self.setup_cluster_workload(dcos_api_install, healthcheck_app, dns_app, viplisten_app, viptalk_app)

        with logger.scope("upgrade cluster"):
            test_util.cluster.upgrade_dcos(cluster, self.installer_url,
                                           installed_version, add_config_path=self.config_yaml_override_upgrade)
            with cluster.ssher.tunnel(cluster.bootstrap_host) as bootstrap_host_tunnel:
                bootstrap_host_tunnel.remote_cmd(['sudo', 'rm', '-rf', cluster.ssher.home_dir + '/*'])

        # this method invocation looks like it is the same as the one above, and that is partially correct.
        # the arguments to the invocation are the same, but the thing that changes is the lifecycle of the cluster
        # the client is being created to interact with. This client is specifically for the cluster after the
        # upgrade has taken place, and can account for any possible settings that may change for the client under
        # the hood when it probes the cluster.
        dcos_api_upgrade = self.dcos_api_session_factory_upgrade.apply(
            'http://{ip}'.format(ip=cluster.masters[0].public_ip),
            master_list,
            master_list,
            [h.private_ip for h in cluster.agents],
            [h.private_ip for h in cluster.public_agents],
            self.default_os_user)

        dcos_api_upgrade.wait_for_dcos()  # here we wait for DC/OS to be "up" so that we can auth this new client

        self.verify_apps_state(dcos_api_upgrade, dns_app)

        with logger.scope("run integration tests"):
            # copied from test_util/test_aws_cf.py:96
            add_env = []
            prefix = 'TEST_ADD_ENV_'
            for k, v in os.environ.items():
                if k.startswith(prefix):
                    add_env.append(k.replace(prefix, '') + '=' + v)
            test_cmd = ' '.join(add_env) + ' py.test -vv -s -rs ' + os.getenv('CI_FLAGS', '')
            result = test_util.cluster.run_integration_tests(cluster, test_cmd=test_cmd)

        if result == 0:
            self.log.info("Test successful! Deleting VPC if provided in this run.")
            vpc.delete()
            bw.delete_key_pair(stack_name)
        else:
            self.log.info("Test failed! VPC cluster will remain available for "
                          "debugging for 2 hour after instantiation.")
            if os.getenv('CI_FLAGS'):
                result = 0

        return result


class DcosApiSessionFactory(VpcClusterUpgradeTestDcosApiSessionFactory):
    def apply(self, dcos_url: str, masters: List[str], public_masters: List[str], slaves: List[str],
              public_slaves: List[str], default_os_user: str) -> DcosApiSession:
        return DcosApiSession(dcos_url, masters, public_masters, slaves, public_slaves,
                              default_os_user, DcosUser(CI_CREDENTIALS))


def main():
    num_masters = int(os.getenv('MASTERS', '3'))
    num_agents = int(os.getenv('AGENTS', '2'))
    num_public_agents = int(os.getenv('PUBLIC_AGENTS', '1'))

    stable_installer_url = os.environ['STABLE_INSTALLER_URL']
    installer_url = os.environ['INSTALLER_URL']
    aws_region = os.getenv('DEFAULT_AWS_REGION', 'eu-central-1')
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')

    config_yaml_override_install = os.getenv('CONFIG_YAML_OVERRIDE_INSTALL')
    config_yaml_override_upgrade = os.getenv('CONFIG_YAML_OVERRIDE_UPGRADE')

    dcos_api_session_factory = DcosApiSessionFactory()
    test = VpcClusterUpgradeTest(num_masters, num_agents, num_public_agents,
                                 stable_installer_url, installer_url,
                                 aws_region, aws_access_key_id, aws_secret_access_key,
                                 "root",
                                 config_yaml_override_install, config_yaml_override_upgrade,
                                 dcos_api_session_factory, dcos_api_session_factory)
    status = test.run_test()

    sys.exit(status)
