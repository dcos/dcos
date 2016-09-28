#!/usr/bin/env python3

import logging
import os
import random
import string
import sys

import test_util.aws
import test_util.cluster


logging.basicConfig(format='[%(asctime)s|%(name)s|%(levelname)s]: %(message)s', level=logging.DEBUG)
log = logging.getLogger(__name__)


def main():
    num_masters = int(os.getenv('MASTERS', '3'))
    num_agents = int(os.getenv('AGENTS', '2'))
    num_public_agents = int(os.getenv('PUBLIC_AGENTS', '1'))
    stack_name = 'upgrade-test-' + ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))

    pytest_dir = os.getenv('DCOS_PYTEST_DIR', '/opt/mesosphere/active/dcos-integration-test')
    pytest_cmd = os.getenv('DCOS_PYTEST_CMD', 'py.test -rs -vv ' + os.getenv('CI_FLAGS', ''))

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
        ssh_key_path=os.getenv('DCOS_SSH_KEY_PATH', 'default_ssh_key'),
        num_masters=num_masters,
        num_agents=num_agents,
        num_public_agents=num_public_agents,
    )

    # Use the CLI installer to set exhibitor_storage_backend = zookeeper.
    test_util.cluster.install_dcos(cluster, stable_installer_url, api=False)
    with cluster.ssher.tunnel(cluster.bootstrap_host) as bootstrap_host_tunnel:
        bootstrap_host_tunnel.remote_cmd(['sudo', 'rm', '-rf', cluster.ssher.home_dir + '/*'])
    test_util.cluster.upgrade_dcos(cluster, installer_url)

    result = test_util.cluster.run_integration_tests(cluster, pytest_dir=pytest_dir, pytest_cmd=pytest_cmd)
    if result == 0:
        log.info("Test successsful! Deleting VPC if provided in this run...")
        vpc.delete()
    else:
        log.info("Test failed! VPC will remain for debugging 1 hour from instantiation")
    sys.exit(result)
