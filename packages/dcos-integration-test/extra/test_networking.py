import concurrent.futures
import contextlib
import json
import logging
import random
import threading
import time
from collections import deque
from subprocess import check_output

import pytest
import requests
import retrying

from pkgpanda.build import load_json
from test_util.marathon import get_test_app


log = logging.getLogger(__name__)
timeout = 500
maxthreads = 16
backend_port_st = 8000


def lb_enabled():
    config = load_json('/opt/mesosphere/etc/expanded.config.json')
    return config['enable_lb'] == 'true'


@retrying.retry(wait_fixed=2000,
                stop_max_delay=timeout * 1000,
                retry_on_result=lambda ret: ret is False,
                retry_on_exception=lambda x: True)
def ensure_routable(cmd, host, port):
    proxy_uri = 'http://{}:{}/run_cmd'.format(host, port)
    log.info('Sending {} data: {}'.format(proxy_uri, cmd))
    r = requests.post(proxy_uri, data=cmd)
    log.info('Requests Response: %s', repr(r.json()))
    assert r.json()['status'] == 0
    return json.loads(r.json()['output'])


class VipTest:
    def __init__(self, num, container, vip, vipaddr, samehost, vipnet, proxynet):
        self.num = num
        self.vip = vip.format(num, 7000 + num)
        self.vipaddr = vipaddr.format(num, 7000 + num)
        self.container = container
        self.samehost = samehost
        self.vipnet = vipnet
        self.proxynet = proxynet
        self.notes = ""

    def __str__(self):
        return ('VipTest(container={}, vip={},vipaddr={},samehost={},'
                'vipnet={},proxynet={}, notes={})').format(self.container, self.vip, self.vipaddr, self.samehost,
                                                           self.vipnet, self.proxynet, self.notes)

    def log(self, s, lvl=logging.DEBUG):
        m = 'VIP_TEST {} {}'.format(s, self)
        log.log(lvl, m)


def vip_app(num, container, network, host, vip):
    if network in ['HOST', 'BRIDGE']:
        # both of these cases will rely on marathon to assign ports
        return get_test_app(
            network=network,
            host_constraint=host,
            vip=vip,
            container_type=container)
    elif network == 'USER':
        # ports must be incremented as one shared network is used
        return get_test_app(
            network=network,
            host_port=backend_port_st + num,
            container_port=backend_port_st + num,
            host_constraint=host,
            vip=vip,
            container_type=container)
    else:
        raise AssertionError('Unexpected network: {}'.format(network))


def vip_test(dcos_api_session, r):
    r.log('START')
    agents = list(dcos_api_session.all_slaves)
    # make sure we can reproduce
    random.seed(r.vip)
    random.shuffle(agents)
    host1 = agents[0]
    host2 = agents[0]
    if not r.samehost:
        host2 = agents[1]
    log.debug('host1 is is: {}'.format(host1))
    log.debug('host2 is is: {}'.format(host2))

    origin_app, app_uuid = vip_app(r.num, r.container, r.vipnet, host1, r.vip)
    # allow to run on both public and private agents
    origin_app['acceptedResourceRoles'] = ["*", "slave_public"]
    proxy_app, _ = vip_app(r.num, r.container, r.proxynet, host2, None)
    # allow to run on both public and private agents
    proxy_app['acceptedResourceRoles'] = ["*", "slave_public"]

    returned_uuid = None
    with contextlib.ExitStack() as stack:
        # try to avoid thundering herd
        time.sleep(random.randint(0, 30))
        stack.enter_context(dcos_api_session.marathon.deploy_and_cleanup(origin_app, timeout=timeout))
        sp = stack.enter_context(dcos_api_session.marathon.deploy_and_cleanup(proxy_app, timeout=timeout))
        proxy_host = sp[0].host
        proxy_port = sp[0].port
        if proxy_port == 0 and sp[0].ip is not None:
            proxy_port = backend_port_st + r.num
            proxy_host = sp[0].ip
        log.info("proxy endpoints are {}".format(sp))
        cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}/test_uuid'.format(r.vipaddr)
        returned_uuid = ensure_routable(cmd, proxy_host, proxy_port)
        log.debug('returned_uuid is: {}'.format(returned_uuid))
    assert returned_uuid is not None
    assert returned_uuid['test_uuid'] == app_uuid
    r.log('PASSED')


@pytest.fixture
def reduce_logging():
    start_log_level = logging.getLogger('test_util.marathon').getEffectiveLevel()
    # gotta go up to warning to mute it as its currently at info
    logging.getLogger('test_util.marathon').setLevel(logging.WARNING)
    yield
    logging.getLogger('test_util.marathon').setLevel(start_log_level)


@pytest.mark.skipif(not lb_enabled(), reason='Load Balancer disabled')
def test_vip(dcos_api_session, reduce_logging):
    '''Test VIPs between the following source and destination configurations:
        * containers: DOCKER, UCR and NONE
        * networks: USER, BRIDGE (docker only), HOST
        * agents: source and destnations on same agent or different agents
        * vips: named and unnamed vip

    '''
    addrs = [['1.1.1.{}:{}', '1.1.1.{}:{}'],
             ['/namedvip{}:{}', 'namedvip{}.marathon.l4lb.thisdcos.directory:{}']]
    # tests
    # UCR doesn't support BRIDGE mode
    permutations = [[c, vi, va, sh, vn, pn]
                    for c in [None, 'MESOS', 'DOCKER']
                    for [vi, va] in addrs
                    for sh in [True, False]
                    for vn in ['USER', 'BRIDGE', 'HOST']
                    for pn in ['USER', 'BRIDGE', 'HOST']]
    tests = [VipTest(i, c, vi, va, sh, vn, pn) for i, [c, vi, va, sh, vn, pn] in enumerate(permutations)]
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=maxthreads)
    # deque is thread safe
    failed_tests = deque(tests)
    passed_tests = deque()
    skipped_tests = deque()
    # skip certain tests
    for r in tests:
        if r.container == 'UCR' or r.container == 'NONE':
            if r.vipnet == 'BRIDGE' or r.proxynet == 'BRIDGE':
                r.notes = "bridge networks are not supported by mesos runtime"
                failed_tests.remove(r)
                skipped_tests.append(r)
                continue
        if not r.samehost and len(dcos_api_session.all_slaves) == 1:
            r.notes = "needs more then 1 agent to run"
            failed_tests.remove(r)
            skipped_tests.append(r)

    def run(test):
        vip_test(dcos_api_session, test)
        failed_tests.remove(test)
        passed_tests.append(test)

    tasks = [executor.submit(run, t) for t in failed_tests]
    for t in concurrent.futures.as_completed(tasks):
        try:
            t.result()
        except Exception as exc:
            # just log the exception, each failed test is recored in the `failed_tests` array
            log.info('vip_test generated an exception: {}'.format(exc))
    [r.log('PASSED', lvl=logging.INFO) for r in passed_tests]
    [r.log('SKIPPED', lvl=logging.INFO) for r in skipped_tests]
    [r.log('FAILED', lvl=logging.INFO) for r in failed_tests]
    log.info('VIP_TEST num agents: {}'.format(len(dcos_api_session.all_slaves)))
    assert len(failed_tests) == 0


@retrying.retry(wait_fixed=2000,
                stop_max_delay=timeout * 1000,
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
def test_if_minuteman_disabled(dcos_api_session):
    '''Test to make sure minuteman is disabled'''
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
