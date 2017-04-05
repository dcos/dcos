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

from test_util.marathon import get_test_app

log = logging.getLogger(__name__)


def lb_enabled():
    return expanded_config['enable_lb'] == 'true'


@retrying.retry(wait_fixed=2000,
                stop_max_delay=90 * 1000,
                retry_on_result=lambda ret: ret is False,
                retry_on_exception=lambda x: True)
def ensure_routable(cmd, host, port):
    proxy_uri = 'http://{}:{}/run_cmd'.format(host, port)
    log.info('Sending {} data: {}'.format(proxy_uri, cmd))
    r = requests.post(proxy_uri, data=cmd)
    log.info('Requests Response: %s', repr(r.json()))
    assert r.json()['status'] == 0
    return json.loads(r.json()['output'])


def vip_app(container, network, host, vip, second):
    if network in ['HOST', 'BRIDGE']:
        # both of these cases will rely on marathon to assign ports
        return get_test_app(
            network=network,
            host_constraint=host,
            vip=vip,
            container_type=container)
    elif network == 'USER':
        # ports must be incremented as one shared network is used
        user_port = 8000 if not second else 8001
        return get_test_app(
            network=network,
            host_port=user_port,
            host_constraint=host,
            vip=vip,
            container_type=container)
    else:
        raise AssertionError('Unexpected network: {}'.format(network))


def generate_vip_app_permutations():
    """ Generate all possible network interface permutations for applying vips
    """
    permutations = []
    for container in [None, 'MESOS', 'DOCKER']:
        for named_vip in [True, False]:
            for same_host in [True, False]:
                for vip_net in ['USER', 'BRIDGE', 'HOST']:
                    for proxy_net in ['USER', 'BRIDGE', 'HOST']:
                        if container != 'DOCKER' and 'BRIDGE' in (vip_net, proxy_net):
                            # only DOCKER containers support BRIDGE network
                            continue
                        permutations.append((container, named_vip, same_host, vip_net, proxy_net))
    return permutations


@pytest.mark.skipif(not lb_enabled(), reason='Load Balancer disabled')
@pytest.mark.parametrize('container,named_vip,same_host,vip_net,proxy_net', generate_vip_app_permutations())
def test_vip(dcos_api_session, container, named_vip, same_host, vip_net, proxy_net):
    '''Test VIPs between the following source and destination configurations:
        * containers: DOCKER, UCR and NONE
        * networks: USER, BRIDGE (docker only), HOST
        * agents: source and destnations on same agent or different agents
        * vips: named and unnamed vip

    Origin app will be deployed to the cluster with a VIP. Proxy app will be
    deployed either to the same host or else where. Finally, a thread will be
    started on localhost (which should be a master) to submit a command to the
    proxy container that will ping the origin container VIP and then assert
    that the expected origin app UUID was returned
    '''
    if not same_host and len(dcos_api_session.all_slaves) == 1:
        pytest.skip("must have more than one agent for this test!")
    if named_vip:
        vip = '/namedvip:7000'
        vipaddr = 'namedvip.marathon.l4lb.thisdcos.directory:7000'
    else:
        vip = '1.1.1.7:7000'
        vipaddr = '1.1.1.7:7000'

    agents = list(dcos_api_session.all_slaves)
    # make sure we can reproduce
    random.seed(vip)
    random.shuffle(agents)
    host1 = agents[0]
    if not same_host:
        host2 = agents[1]
    else:
        host2 = agents[0]
    origin_app, app_uuid = vip_app(container, vip_net, host1, vip, False)
    proxy_app, _ = vip_app(container, proxy_net, host2, None, True)
    # allow these apps to run on public slaves
    origin_app['acceptedResourceRoles'] = ['*', 'slave_public']
    proxy_app['acceptedResourceRoles'] = ['*', 'slave_public']
    returned_uuid = None
    with contextlib.ExitStack() as stack:
        # We do not need the service endpoint of the origin app because it has the VIP,
        stack.enter_context(dcos_api_session.marathon.deploy_and_cleanup(origin_app, check_health=False))
        endpoints = stack.enter_context(dcos_api_session.marathon.deploy_and_cleanup(proxy_app))
        endpoint = endpoints[0]
        if proxy_net == 'USER':
            host = endpoint.ip
            port = 8001
        else:
            host = endpoint.host
            port = endpoint.port
        cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}/test_uuid'.format(vipaddr)
        returned_uuid = ensure_routable(cmd, host, port)
    assert returned_uuid is not None
    assert returned_uuid['test_uuid'] == app_uuid


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
    app_definition, test_uuid = get_test_app(container_type='DOCKER', network='USER', host_port=9080)

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
