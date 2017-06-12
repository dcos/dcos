import collections
import contextlib
import json
import logging
import random
import threading
from collections import deque
from subprocess import check_output

import pytest
import requests
import retrying

from test_helpers import expanded_config

from test_util.marathon import Container, get_test_app, Network

log = logging.getLogger(__name__)

GLOBAL_PORT_POOL = collections.defaultdict(lambda: list(range(10000, 32000)))


def unused_port(network):
    global GLOBAL_PORT_POOL
    return GLOBAL_PORT_POOL[network].pop(random.choice(range(len(GLOBAL_PORT_POOL[network]))))


def lb_enabled():
    return expanded_config['enable_lb'] == 'true'


@retrying.retry(wait_fixed=2000,
                stop_max_delay=90 * 1000,
                retry_on_result=lambda ret: ret is False,
                retry_on_exception=lambda x: True)
def ensure_routable(cmd, host, port):
    proxy_uri = 'http://{}:{}/run_cmd'.format(host, port)
    log.debug('Sending {} data: {}'.format(proxy_uri, cmd))
    r = requests.post(proxy_uri, data=cmd)
    log.debug('Requests Response: %s', repr(r.json()))
    assert r.json()['status'] == 0
    return json.loads(r.json()['output'])


def vip_app(container: Container, network: Network, host: str, vip: str):
    # user_net_port is only actually used for USER network because this cannot be assigned
    # by marathon
    if network in [Network.HOST, Network.BRIDGE]:
        # both of these cases will rely on marathon to assign ports
        return get_test_app(
            network=network,
            host_constraint=host,
            vip=vip,
            container_type=container)
    elif network == Network.USER:
        return get_test_app(
            network=network,
            host_port=unused_port(Network.USER),
            host_constraint=host,
            vip=vip,
            container_type=container)
    else:
        raise AssertionError('Unexpected network: {}'.format(network.value))


def generate_vip_app_permutations():
    """ Generate all possible network interface permutations for applying vips
    """
    network_options = [Network.USER, Network.BRIDGE, Network.HOST]
    permutations = []
    for container in [Container.NONE, Container.MESOS, Container.DOCKER]:
        for vip_net in network_options:
            for proxy_net in network_options:
                if container != Container.DOCKER and Network.BRIDGE in (vip_net, proxy_net):
                    # only DOCKER containers support BRIDGE network
                    continue
                permutations.append((container, vip_net, proxy_net))
    return permutations


@pytest.fixture(scope='module')
def clean_state_for_test_vip(dcos_api_session):
    """ This fixture is intended only for use with only test_vip so that the
    test suite only blocks on ensuring marathon has a clean state before and
    after the all test_vip cases are invoked rather than per-case
    """
    dcos_api_session.marathon.ensure_deployments_complete()
    yield
    dcos_api_session.marathon.ensure_deployments_complete()


@pytest.mark.slow
@pytest.mark.skipif(not lb_enabled(), reason='Load Balancer disabled')
@pytest.mark.parametrize('container,vip_net,proxy_net', generate_vip_app_permutations())
@pytest.mark.usefixtures('clean_state_for_test_vip')
def test_vip(dcos_api_session, container: Container, vip_net: Network, proxy_net: Network):
    '''Test VIPs between the following source and destination configurations:
        * containers: DOCKER, UCR and NONE
        * networks: USER, BRIDGE (docker only), HOST
        * agents: source and destnations on same agent or different agents
        * vips: named and unnamed vip

    Origin app will be deployed to the cluster with a VIP. Proxy app will be
    deployed either to the same host or elsewhere. Finally, a thread will be
    started on localhost (which should be a master) to submit a command to the
    proxy container that will ping the origin container VIP and then assert
    that the expected origin app UUID was returned
    '''
    failure_stack = []
    for test in setup_vip_workload_tests(dcos_api_session, container, vip_net, proxy_net):
        cmd, origin_app, proxy_app, proxy_net = test
        log.info('Deploying origin app')
        wait_for_tasks_healthy(dcos_api_session, origin_app)
        log.info('Origin app successful, deploying proxy app..')
        proxy_info = wait_for_tasks_healthy(dcos_api_session, proxy_app)
        proxy_task_info = proxy_info['app']['tasks'][0]
        if proxy_net == Network.USER:
            proxy_host = proxy_task_info['ipAddresses'][0]['ipAddress']
            if container == Container.DOCKER:
                proxy_port = proxy_task_info['ports'][0]
            else:
                proxy_port = proxy_app['ipAddress']['discovery']['ports'][0]['number']
        else:
            proxy_host = proxy_task_info['host']
            proxy_port = proxy_task_info['ports'][0]
        try:
            assert ensure_routable(cmd, proxy_host, proxy_port)['test_uuid'] == origin_app['env']['DCOS_TEST_UUID']
        except Exception as ex:
            failure_stack.append('RemoteCommand:{}\n\nOriginApp:{}\n\nProxyApp:{}\n\nException:'.format(*test))
            failure_stack.append(str(repr(ex)))
        dcos_api_session.marathon.delete('v2/apps/{}'.format(origin_app['id']))
        dcos_api_session.marathon.delete('v2/apps/{}'.format(proxy_app['id']))
    if len(failure_stack) > 0:
        raise AssertionError('\n******************************************\n'.join(failure_stack))


def setup_vip_workload_tests(dcos_api_session, container, vip_net, proxy_net):
    if len(dcos_api_session.all_slaves) < 2:
        pytest.skip('must have more than one agent for this test!')
    apps = list()
    tests = list()
    for named_vip in (True, False):
        for same_host in (True, False):
            if named_vip:
                origin_host = dcos_api_session.all_slaves[0]
                proxy_host = dcos_api_session.all_slaves[1]
                vip_port = unused_port('namedvip')
                vip = '/namedvip:{}'.format(vip_port)
                vipaddr = 'namedvip.marathon.l4lb.thisdcos.directory:{}'.format(vip_port)
            else:
                origin_host = dcos_api_session.all_slaves[1]
                proxy_host = dcos_api_session.all_slaves[0]
                vip_port = unused_port('1.1.1.7')
                vip = '1.1.1.7:{}'.format(vip_port)
                vipaddr = vip
            if same_host:
                proxy_host = origin_host
            cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}/test_uuid'.format(vipaddr)
            origin_app, origin_app_uuid = vip_app(container, vip_net, origin_host, vip)
            proxy_app, proxy_app_uuid = vip_app(container, proxy_net, proxy_host, None)
            # allow these apps to run on public slaves
            origin_app['acceptedResourceRoles'] = ['*', 'slave_public']
            proxy_app['acceptedResourceRoles'] = ['*', 'slave_public']
            # We do not need the service endpoints because we have deterministically assigned them
            for app_definition in (origin_app, proxy_app):
                r = dcos_api_session.marathon.post('v2/apps', json=app_definition)
                r.raise_for_status()
                apps.append(app_definition)
            tests.append((cmd, origin_app, proxy_app, proxy_net))
    return tests


@retrying.retry(
    wait_fixed=5000,
    stop_max_delay=360 * 1000,
    # the app monitored by this function typically takes 2 minutes when starting from
    # a fresh state, but in this case the previous app load may still be winding down,
    # so allow a larger buffer time
    retry_on_result=lambda res: res is None)
def wait_for_tasks_healthy(dcos_api_session, app_definition):
    proxy_info = dcos_api_session.marathon.get('v2/apps/{}'.format(app_definition['id'])).json()
    if proxy_info['app']['tasksHealthy'] == app_definition['instances']:
        return proxy_info
    return None


@retrying.retry(wait_fixed=2000,
                stop_max_delay=120 * 1000,
                retry_on_exception=lambda x: True)
def test_if_overlay_ok(dcos_api_session):
    def _check_overlay(hostname, port):
        overlays = dcos_api_session.get('overlay-agent/overlay', host=hostname, port=port).json()['overlays']
        assert len(overlays) > 0
        for overlay in overlays:
            assert overlay['state']['status'] == 'STATUS_OK'

    for master in dcos_api_session.masters:
        _check_overlay(master, 5050)
    for slave in dcos_api_session.all_slaves:
        _check_overlay(slave, 5051)


@pytest.mark.skipif(lb_enabled(), reason='Load Balancer enabled')
def test_if_navstar_l4lb_disabled(dcos_api_session):
    '''Test to make sure navstar_l4lb is disabled'''
    data = check_output(['/usr/bin/env', 'ip', 'rule'])
    # Minuteman creates this ip rule: `9999: from 9.0.0.0/8 lookup 42`
    # We check it doesn't exist
    assert str(data).find('9999') == -1


def test_ip_per_container(dcos_api_session):
    '''Test if we are able to connect to a task with ip-per-container mode
    '''
    # Launch the test_server in ip-per-container mode (user network)
    app_definition, test_uuid = get_test_app(container_type=Container.DOCKER, network=Network.USER, host_port=9080)

    assert len(dcos_api_session.slaves) >= 2, 'IP Per Container tests require 2 private agents to work'

    app_definition['instances'] = 2
    app_definition['constraints'] = [['hostname', 'UNIQUE']]

    with dcos_api_session.marathon.deploy_and_cleanup(app_definition, check_health=True) as service_points:
        app_port = app_definition['container']['docker']['portMappings'][0]['containerPort']
        cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}:{}/ping'.format(service_points[1].ip, app_port)
        ensure_routable(cmd, service_points[0].host, service_points[0].port)


@retrying.retry(wait_fixed=2000,
                stop_max_delay=100 * 2000,
                retry_on_exception=lambda x: True)
def geturl(url):
    rs = requests.get(url)
    assert rs.status_code == 200
    r = rs.json()
    log.info('geturl {} -> {}'.format(url, r))
    return r


@pytest.mark.skipif(not lb_enabled(), reason='Load Balancer disabled')
def test_l4lb(dcos_api_session):
    '''Test l4lb is load balancing between all the backends
       * create 5 apps using the same VIP
       * get uuid from the VIP in parallel from many threads
       * verify that 5 uuids have been returned
       * only testing if all 5 are hit at least once
    '''
    numapps = 5
    numthreads = numapps * 4
    apps = []
    rvs = deque()
    with contextlib.ExitStack() as stack:
        for _ in range(numapps):
            origin_app, origin_uuid = get_test_app()
            # same vip for all the apps
            origin_app['portDefinitions'][0]['labels'] = {'VIP_0': '/l4lbtest:5000'}
            apps.append(origin_app)
            sp = stack.enter_context(dcos_api_session.marathon.deploy_and_cleanup(origin_app))
            # make sure that the service point responds
            geturl('http://{}:{}/ping'.format(sp[0].host, sp[0].port))
            # make sure that the VIP is responding too
            geturl('http://l4lbtest.marathon.l4lb.thisdcos.directory:5000/ping')

        # do many requests in parallel.
        def thread_request():
            # deque is thread safe
            rvs.append(geturl('http://l4lbtest.marathon.l4lb.thisdcos.directory:5000/test_uuid'))

        threads = [threading.Thread(target=thread_request) for i in range(0, numthreads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    expected_uuids = [a['id'].split('-')[2] for a in apps]
    received_uuids = [r['test_uuid'] for r in rvs if r is not None]
    assert len(set(expected_uuids)) == numapps
    assert len(set(received_uuids)) == numapps
    assert set(expected_uuids) == set(received_uuids)
