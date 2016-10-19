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

"""
import collections
import datetime
import logging
import os
import random
import string
import sys
import uuid

import test_util.aws
import test_util.cluster
from pkgpanda.util import load_string
from test_util.cluster_api import ClusterApi
from test_util.helpers import CI_AUTH_JSON, DcosUser
from test_util.marathon import TEST_APP_NAME_FMT

logging.basicConfig(format='[%(asctime)s|%(name)s|%(levelname)s]: %(message)s', level=logging.DEBUG)
log = logging.getLogger(__name__)


def get_test_app():
    app = {
        "id": TEST_APP_NAME_FMT.format(uuid.uuid4().hex),
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
                "intervalSeconds": 10,
                "timeoutSeconds": 10,
                "maxConsecutiveFailures": 3
            }
        ],
    }
    return app


def get_task_info(apps, tasks):
    idx = 0    # We have a single app and a task for this test.

    try:
        tasks_state = tasks["tasks"][idx]["state"]
        health_check_interval = \
            apps["apps"][idx]["healthChecks"][idx]["intervalSeconds"]
        task_id = tasks["tasks"][idx]["id"]
        last_success = tasks["tasks"][idx]["healthCheckResults"][idx]["lastSuccess"]
    except IndexError as e:
        logging.debug("Failed to get task detail: {exp}".format(exp=str(e)))
        return None

    TaskInfo = collections.namedtuple("TaskInfo", "state id health_check_interval last_success_time")

    task_info = TaskInfo(
        state=tasks_state,
        id=task_id,
        health_check_interval=datetime.timedelta(seconds=health_check_interval),
        last_success_time=(datetime.datetime.strptime(last_success, "%Y-%m-%dT%H:%M:%S.%fZ")))

    return task_info


def main():
    num_masters = int(os.getenv('MASTERS', '3'))
    num_agents = int(os.getenv('AGENTS', '2'))
    num_public_agents = int(os.getenv('PUBLIC_AGENTS', '1'))
    stack_name = 'upgrade-test-' + ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))

    test_cmd = os.getenv('DCOS_PYTEST_CMD', 'py.test -vv -s -rs ' + os.getenv('CI_FLAGS', ''))

    stable_installer_url = os.environ['STABLE_INSTALLER_URL']
    installer_url = os.environ['INSTALLER_URL']

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
    test_util.cluster.install_dcos(cluster, stable_installer_url, api=False)

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

    # Deploy an app
    cluster_api.marathon.deploy_app(get_test_app())

    task_info_before_upgrade = get_task_info(cluster_api.marathon.get('v2/apps').json(),
                                             cluster_api.marathon.get('v2/tasks').json())

    assert task_info_before_upgrade is not None, "Unable to get task details of the cluster."
    assert task_info_before_upgrade.state == "TASK_RUNNING", "Task is not in the running state."

    with cluster.ssher.tunnel(cluster.bootstrap_host) as bootstrap_host_tunnel:
        bootstrap_host_tunnel.remote_cmd(['sudo', 'rm', '-rf', cluster.ssher.home_dir + '/*'])

    test_util.cluster.upgrade_dcos(cluster, installer_url)

    task_info_after_upgrade = get_task_info(cluster_api.marathon.get('v2/apps').json(),
                                            cluster_api.marathon.get('v2/tasks').json())

    assert task_info_after_upgrade is not None, "Unable to get the tasks details of the cluster."
    assert task_info_after_upgrade.state == "TASK_RUNNING", "Task is not in the running state."

    assert task_info_before_upgrade.id == task_info_after_upgrade.id, \
        "Task ID before and after the upgrade did not match."

    # There has happened at least one health-check in the new cluster since the last health-check in the old cluster.
    assert (task_info_after_upgrade.last_success_time >
            task_info_before_upgrade.last_success_time + task_info_before_upgrade.health_check_interval), \
        "Invalid health-check for the task in the upgraded cluster."

    result = test_util.cluster.run_integration_tests(cluster, test_cmd=test_cmd)

    if result == 0:
        log.info("Test successsful! Deleting VPC if provided in this run...")
        vpc.delete()
    else:
        log.info("Test failed! VPC cluster will remain available for debugging for 2 hour after instantiation.")
    sys.exit(result)
