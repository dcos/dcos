import logging
import os
import subprocess

import pytest
import requests
import retrying
import test_util.aws


resiliency = pytest.mark.skipif(
    not pytest.config.getoption("--resiliency"),
    reason="need --resiliency to run")


def verify_test_app(url):
    logging.info('Attempting to ping test application')
    r = requests.get('http://{}/ping'.format(url))
    assert r.ok, 'Bad response from test server: ' + str(r.status_code)
    assert r.json() == {"pong": True}, 'Unexpected response from server: ' + repr(r.json())


@pytest.fixture
def persistent_app(cluster):
    """Raise exception if env not set and then start
    a marathon job
    """
    test_app, _ = cluster.get_test_app()
    test_app['portDefinitions'][0]['labels'] = {
        'VIP_0': '6.6.6.1:6661',
        'VIP_1': test_app['id'][1:] + ':12345'}
    with cluster.marathon_deploy_and_cleanup(test_app):
        # Service points don't help as the app will likely be
        # started elsewhere after an agent failure
        return test_app


@pytest.fixture(scope='session')
def provider(cluster):
    """Interface for direct interation to provider hardware
    Currently only supports AWS CF with AWS VPC coming soon
    """
    if cluster.provider != 'aws':
        pytest.skip()
    aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']
    aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']
    aws_region = os.environ['AWS_REGION']
    stack_name = os.environ['AWS_STACK_NAME']
    bw = test_util.aws.BotoWrapper(aws_region, aws_access_key_id, aws_secret_access_key)
    return test_util.aws.DcosCfSimple(stack_name, bw)


@retrying.retry(wait_fixed=3000, stop_max_delay=600 * 1000,
                retry_on_result=lambda res: res is False,
                retry_on_exception=lambda ex: False)
def wait_for_agents(cluster):
    r = cluster.get('/mesos/master/slaves')
    assert r.status_code == 200
    data = r.json()
    slaves_ids = sorted(x['id'] for x in data['slaves'])
    for slave_id in slaves_ids:
        uri = '/slave/{}/slave%281%29/state.json'.format(slave_id)
        r = cluster.get(uri)
        if r.status_code >= 400:
            # slave is still coming up, so failure is expected
            logging.info('Slave with-id {} returning code {}'.format(slave_id, r.status_code))
            return False
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["id"] == slave_id


@retrying.retry(wait_fixed=3000, stop_max_delay=300 * 1000)
def wait_for_persistent_app(url):
    verify_test_app(url)


@resiliency
def test_agent_failure(provider, cluster, persistent_app):
    logging.info('Shutting down all agents across cluster...')
    public_agents = provider.get_tag_instances('PublicSlaveServerGroup')
    private_agents = provider.get_tag_instances('SlaveServerGroup')
    agents = []
    for agent in public_agents + private_agents:
        agents.append(agent['InstanceId'])
    # Agents are in autoscaling groups, so they will automatically be replaced
    provider.boto_wrapper.client('ec2').terminate_instances(InstanceIds=agents)
    logging.info('Restarting the cluster agents...')
    # will verify that all agents have rejoined the cluster
    wait_for_agents(cluster)
    # verify that everything else is still working
    cluster._wait_for_dcos()
    # finally verify that the app is again running somewhere with its VIPs
    wait_for_persistent_app(persistent_app['portDefinitions'][0]['labels']['VIP_0'])
    wait_for_persistent_app(persistent_app['portDefinitions'][0]['labels']['VIP_1'])


@pytest.fixture
def masters_down(provider):
    this_master = subprocess.checkout(['/opt/mesosphere/bin/detect-ip'])
    assert this_master
