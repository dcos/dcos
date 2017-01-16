#!/usr/bin/env python3
"""Integration test for onprem DC/OS upgraded from latest stable.

The following environment variables control test procedure:

MASTERS: integer (default=3)
    The number of masters to create from a newly created VPC.

AGENTS: integer (default=2)
    The number of agents to create from a newly created VPC.

PUBLIC_AGENTS: integer (default=1)
    The number of public agents to create from a newly created VPC.

DCOS_SSH_KEY_PATH: string (default='default_ssh_key')
    Use to set specific ssh key path. Otherwise, script will expect key at default_ssh_key

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
import random
import string
import sys
import uuid
from contextlib import contextmanager

import retrying

import test_util.aws
import test_util.cluster
from pkgpanda.util import load_string
from test_util.cluster_api import ClusterApi
from test_util.helpers import CI_AUTH_JSON, DcosUser


logging.basicConfig(format='[%(asctime)s|%(name)s|%(levelname)s]: %(message)s', level=logging.DEBUG)
log = logging.getLogger(__name__)


TEST_APP_NAME_FMT = 'upgrade-{}'


def app_id_to_mesos_dns_name(app_id):
    return '-'.join(reversed(app_id.strip('/').split('/')))


@contextmanager
def cluster_workload(cluster_api):
    """Start a cluster workload on entry and verify its health on exit."""

    def _apps():
        """Return a list of all appIds."""
        response = cluster_api.marathon.get('/v2/apps')
        response.raise_for_status()
        apps = response.json()['apps']
        return sorted(item['id'] for item in apps)

    def _app_tasks(app_id):
        """Return a list of Mesos task IDs for app_id's running tasks."""
        assert app_id.startswith('/')
        response = cluster_api.marathon.get('/v2/apps' + app_id + '/tasks')
        response.raise_for_status()
        tasks = response.json()['tasks']
        return sorted(task['id'] for task in tasks)

    def _info():
        """Return the Marathon info."""
        response = cluster_api.marathon.get('/v2/info')
        response.raise_for_status()
        info = response.json()
        return info

    @retrying.retry(
        wait_fixed=(1 * 1000),
        stop_max_delay=(120 * 1000),
        retry_on_result=lambda x: not x)
    def _wait_for_dns(hostname):
        """Return True if Mesos-DNS has at least one entry for hostname."""
        hosts = cluster_api.get('/mesos_dns/v1/hosts/' + hostname).json()
        return any(h['host'] != '' and h['ip'] != '' for h in hosts)

    test_id = uuid.uuid4().hex

    # HTTP healthcheck app to make sure tasks are reachable during the upgrade.
    # If a task fails its healthcheck, Marathon will terminate it and we'll
    # notice it was killed when we check tasks on exit.
    healthcheck_app = {
        "id": '/' + TEST_APP_NAME_FMT.format('healthcheck-' + test_id),
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

    # DNS resolution app to make sure DNS is available during the upgrade.
    # Periodically resolves the healthcheck app's domain name and dies if it
    # fails.
    dns_app = {
        "id": '/' + TEST_APP_NAME_FMT.format('dns-' + test_id),
        "cmd": """
while true
do
    printf "%s " $(date --utc -Iseconds) >> $MESOS_SANDBOX/dns_resolve_log.txt
    if host -W 1 $RESOLVE_NAME
    then
        echo SUCCESS >> $MESOS_SANDBOX/dns_resolve_log.txt
    else
        echo FAILURE >> $MESOS_SANDBOX/dns_resolve_log.txt
    fi
    sleep $INTERVAL_SECONDS
done
""",
        "env": {
            'RESOLVE_NAME': app_id_to_mesos_dns_name(healthcheck_app['id']) + '.marathon.mesos',
            'INTERVAL_SECONDS': '1',
        },
        "cpus": 0.5,
        "mem": 32.0,
        "instances": 1,
        "container": {
            "type": "DOCKER",
            "docker": {
                "image": "mapitman/bind-utils",
                "network": "BRIDGE",
            }
        },
        "dependencies": [healthcheck_app['id']],
    }

    # Deploy test apps.
    # TODO(branden): Define apps and deploy_app() such that we can deploy all
    # test apps at once and then block on waiting for them all to finish
    # deploying. Marathon ought to be responsible for deploying apps in the
    # right order and knowing whether they're deployed and stable.
    cluster_api.marathon.deploy_app(healthcheck_app)
    cluster_api.marathon.ensure_deployments_complete()
    # TODO(branden): This is a hack to make sure we don't deploy dns_app before
    # the name it's trying to resolve is available.
    _wait_for_dns(dns_app['env']['RESOLVE_NAME'])
    cluster_api.marathon.deploy_app(dns_app, check_health=False)
    cluster_api.marathon.ensure_deployments_complete()

    test_apps = [healthcheck_app, dns_app]
    test_app_ids = [app['id'] for app in test_apps]

    tasks_start = {app_id: _app_tasks(app_id) for app_id in test_app_ids}
    log.debug('Test app tasks at start:\n' + pprint.pformat(tasks_start))

    for app in test_apps:
        assert app['instances'] == len(tasks_start[app['id']])

    yield

    apps = _apps()
    log.debug('all existent apps:\n' + pprint.pformat(apps))

    info = _info()
    log.debug('info about leading Marathon:\n' + pprint.pformat(info))

    tasks_end = {app_id: _app_tasks(app_id) for app_id in test_app_ids}
    log.debug('Test app tasks at end:\n' + pprint.pformat(tasks_end))

    # Verify that the tasks we started are still running.
    assert tasks_start == tasks_end

    # TODO(branden): Verify DNS


def main():
    num_masters = int(os.getenv('MASTERS', '3'))
    num_agents = int(os.getenv('AGENTS', '2'))
    num_public_agents = int(os.getenv('PUBLIC_AGENTS', '1'))
    stack_name = 'upgrade-test-' + ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))

    test_cmd = os.getenv('DCOS_PYTEST_CMD', 'py.test -vv -s -rs ' + os.getenv('CI_FLAGS', ''))

    stable_installer_url = os.environ['STABLE_INSTALLER_URL']
    installer_url = os.environ['INSTALLER_URL']

    config_yaml_override_install = os.getenv('CONFIG_YAML_OVERRIDE_INSTALL')
    config_yaml_override_upgrade = os.getenv('CONFIG_YAML_OVERRIDE_UPGRADE')

    vpc, ssh_info = test_util.aws.VpcCfStack.create(
        stack_name=stack_name,
        instance_type='m4.xlarge',
        instance_os='cent-os-7-dcos-prereqs',
        # An instance for each cluster node plus the bootstrap.
        instance_count=(num_masters + num_agents + num_public_agents + 1),
        admin_location='0.0.0.0/0',
        key_pair_name='default',
        boto_wrapper=test_util.aws.BotoWrapper(
            region=os.getenv('DEFAULT_AWS_REGION', 'eu-central-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        ),
    )
    vpc.wait_for_stack_creation()
    cluster = test_util.cluster.Cluster.from_vpc(
        vpc,
        ssh_info,
        ssh_key=load_string(os.getenv('DCOS_SSH_KEY_PATH', 'default_ssh_key')),
        num_masters=num_masters,
        num_agents=num_agents,
        num_public_agents=num_public_agents,
    )

    # Use the CLI installer to set exhibitor_storage_backend = zookeeper.
    test_util.cluster.install_dcos(cluster, stable_installer_url, api=False,
                                   add_config_path=config_yaml_override_install)

    master_list = [h.private_ip for h in cluster.masters]

    cluster_api = ClusterApi(
        'http://{ip}'.format(ip=cluster.masters[0].public_ip),
        master_list,
        master_list,
        [h.private_ip for h in cluster.agents],
        [h.private_ip for h in cluster.public_agents],
        "root",             # default_os_user
        web_auth_default_user=DcosUser(CI_AUTH_JSON),
        ca_cert_path=None)

    cluster_api.wait_for_dcos()

    with cluster.ssher.tunnel(cluster.bootstrap_host) as bootstrap_host_tunnel:
        bootstrap_host_tunnel.remote_cmd(['sudo', 'rm', '-rf', cluster.ssher.home_dir + '/*'])

    with cluster_workload(cluster_api):
        test_util.cluster.upgrade_dcos(cluster, installer_url, add_config_path=config_yaml_override_upgrade)

    result = test_util.cluster.run_integration_tests(cluster, test_cmd=test_cmd)

    if result == 0:
        log.info("Test successful! Deleting VPC if provided in this run.")
        vpc.delete()
    else:
        log.info("Test failed! VPC cluster will remain available for debugging for 2 hour after instantiation.")
    sys.exit(result)
