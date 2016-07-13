#!/usr/bin/env python3
"""Module for running integration_test.py inside of a remote cluster
Note: ssh_user must be able to use docker without sudo priveleges
"""
import logging
import sys
from os.path import join
from subprocess import CalledProcessError

from pkgpanda.util import write_string

LOGGING_FORMAT = '[%(asctime)s|%(name)s|%(levelname)s]: %(message)s'
logging.basicConfig(format=LOGGING_FORMAT, level=logging.DEBUG)
log = logging.getLogger(__name__)


def integration_test(
        tunnel, test_dir,
        dcos_dns, master_list, agent_list, public_agent_list,
        test_dns_search, provider, ci_flags,
        aws_access_key_id='', aws_secret_access_key='', region='', add_env=None):
    """Runs integration test on host

    Args:
        test_dir: directory to leave test_wrapper.sh
        dcos_dns: string representing IP of DCOS DNS host
        master_list: string of comma separated master addresses
        agent_list: string of comma separated agent addresses
        test_dns_search: if set to True, test for deployed mesos DNS app
        ci_flags: optional additional string to be passed to test
        provider: (str) either onprem, aws, or azure
        # The following variables correspond to currently disabled tests
        aws_access_key_id: needed for REXRAY tests
        aws_secret_access_key: needed for REXRAY tests
        region: string indicating AWS region in which cluster is running
        add_env: a python dict with any number of key=value assignments to be passed to
            the test environment
    """
    dns_search = 'true' if test_dns_search else 'false'
    test_env = [
        'DCOS_DNS_ADDRESS=http://'+dcos_dns,
        'MASTER_HOSTS='+','.join(master_list),
        'PUBLIC_MASTER_HOSTS='+','.join(master_list),
        'SLAVE_HOSTS='+','.join(agent_list),
        'PUBLIC_SLAVE_HOSTS='+','.join(public_agent_list),
        'DCOS_PROVIDER='+provider,
        'DNS_SEARCH='+dns_search,
        'AWS_ACCESS_KEY_ID='+aws_access_key_id,
        'AWS_SECRET_ACCESS_KEY='+aws_secret_access_key,
        'AWS_REGION='+region]
    if add_env:
        for key, value in add_env.items():
            extra_env = key + '=' + value
            test_env.append(extra_env)

    test_wrapper = """#!/bin/bash
source /opt/mesosphere/environment.export
{env}
cd /opt/mesosphere/active/dcos-integration-test
py.test -vv {ci_flags}
"""
    test_env_str = ''.join(['export '+e+'\n' for e in test_env])
    write_string('test_wrapper.sh', test_wrapper.format(env=test_env_str, ci_flags=ci_flags))

    wrapper_path = join(test_dir, 'test_wrapper.sh')
    log.info('Running integration test...')
    tunnel.write_to_remote('test_wrapper.sh', wrapper_path)
    try:
        tunnel.remote_cmd(['bash', wrapper_path], stdout=sys.stdout.buffer)
    except CalledProcessError as e:
        return e.returncode
    return 0
