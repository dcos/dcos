import concurrent.futures
import contextlib
import copy
import json
import logging
import random
import threading
import uuid
from collections import deque
from enum import Enum
from subprocess import check_output

import pytest
import requests
import retrying

from pkgpanda.build import load_json
from test_util.marathon import get_test_app, get_test_app_in_docker, get_test_app_in_ucr


log = logging.getLogger(__name__)
timeout = 100
# number of worker threads to use to parallelize the vip test
maxthreads = 16
vip_port_base = 7000
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
    log.debug('Sending {} data: {}'.format(proxy_uri, cmd))
    r = requests.post(proxy_uri, data=cmd)
    log.debug('Requests Response: %s', repr(r.json()))
    assert r.json()['status'] == 0
    return json.loads(r.json()['output'])


class VipTest():

    def __init__(self, num: int, container: str, is_named: bool, samehost: bool,
                 vipnet: str, proxynet: str, notes: str='') -> None:
        self.vip = '1.1.1.{}:{}'
        self.vipaddr = self.vip
        if is_named:
            self.vip = '/namedvip{}:{}'
            self.vipaddr = 'namedvip{}.marathon.l4lb.thisdcos.directory:{}'
        self.vip = self.vip.format(num, vip_port_base + num)
        self.vipaddr = self.vipaddr.format(num, vip_port_base + num)
        self.num = num
        self.container = container
        self.samehost = samehost
        self.vipnet = vipnet
        self.proxynet = proxynet
        self.notes = notes

    def __str__(self):
        s = 'VipTest(container={}, vip={},vipaddr={},samehost={},vipnet={},proxynet={}) {}'
        return s.format(self.container, self.vip, self.vipaddr, self.samehost, self.vipnet, self.proxynet,
                        self.notes)

    def log(self, s, lvl=logging.DEBUG):
        m = 'VIP_TEST {} {}'.format(s, self)
        log.log(lvl, m)

    def docker_vip_app(self, network, host, vip):
        app, uuid = get_test_app_in_docker()
        container_port = 9080
        app['id'] = '/viptest/' + app['id']
        app['container']['docker']['network'] = network
        app['mem'] = 16
        app['cpu'] = 0.01
        if network == 'HOST':
            app['cmd'] = '/opt/mesosphere/bin/dcos-shell python '\
                         '/opt/mesosphere/active/dcos-integration-test/util/python_test_server.py $PORT0'
            del app['container']['docker']['portMappings']
            if vip is not None:
                app['portDefinitions'] = [{'labels': {'VIP_0': vip}}]

        else:
            app['cmd'] = '/opt/mesosphere/bin/dcos-shell python '\
                         '/opt/mesosphere/active/dcos-integration-test/util/python_test_server.py'\
                         ' {}'.format(container_port)
            app['container']['docker']['portMappings'] = [{
                'hostPort': 0,
                'containerPort': container_port,
                'protocol': 'tcp',
                'name': 'test',
                'labels': {}
            }]
            if vip is not None:
                app['container']['docker']['portMappings'][0]['labels'] = {'VIP_0': vip}
            if network == 'USER':
                app['ipAddress'] = {'networkName': 'dcos'}

        app['constraints'] = [['hostname', 'CLUSTER', host]]
        return app, uuid

    def mesos_vip_app(self, num, network, host, vip, ucr=False):
        port = backend_port_st + num
        if ucr is False:
            app, uuid = get_test_app()
        else:
            app, uuid = get_test_app_in_ucr()
        app['id'] = '/viptest/' + app['id']
        app['mem'] = 16
        app['cpu'] = 0.01
        app['healthChecks'] = [{
            'protocol': 'MESOS_HTTP',
            'path': '/ping',
            'gracePeriodSeconds': 5,
            'intervalSeconds': 10,
            'timeoutSeconds': 10,
            'maxConsecutiveFailures': 3,
        }]

        assert network != 'BRIDGE'
        if network == 'USER':
            app['ipAddress'] = {
                'discovery': {
                    'ports': [{
                        'protocol': 'tcp',
                        'name': 'test',
                        'number': port,
                    }]
                }
            }
            app['cmd'] = '/opt/mesosphere/bin/dcos-shell python '\
                         '/opt/mesosphere/active/dcos-integration-test/util/python_test_server.py {}'.format(port)
            app['ipAddress']['networkName'] = 'dcos'
            if vip is not None:
                app['ipAddress']['discovery']['ports'][0]['labels'] = {'VIP_0': vip}
            app['healthChecks'][0]['port'] = port
            app['portDefinitions'] = []

        if network == 'HOST':
            app['cmd'] = '/opt/mesosphere/bin/dcos-shell python '\
                         '/opt/mesosphere/active/dcos-integration-test/util/python_test_server.py $PORT0'
            app['portDefinitions'] = [{
                'protocol': 'tcp',
                'port': 0
            }]
            if vip is not None:
                app['portDefinitions'][0]['labels'] = {'VIP_0': vip}
            app['healthChecks'][0]['portIndex'] = 0

        app['constraints'] = [['hostname', 'CLUSTER', host]]
        log.debug('app: {}'.format(json.dumps(app)))
        return app, uuid

    def vip_app(self, num, container, network, host, vip):
        if container == 'UCR':
            return self.mesos_vip_app(num, network, host, vip, ucr=True)
        if container == 'DOCKER':
            return self.docker_vip_app(network, host, vip)
        if container == 'NONE':
            return self.mesos_vip_app(num, network, host, vip, ucr=False)
        assert False, 'unknown container option {}'.format(container)

    def run(self, dcos_api_session):
        self.log('START')
        agents = list(copy.copy(dcos_api_session.all_slaves))
        self.log('seed is {}'.format(hash(self.vip)))
        random.seed(hash(self.vip))
        random.shuffle(agents)
        host1 = agents[0]
        host2 = agents[0]
        if not self.samehost:
            host2 = agents[1]
        log.debug('host1 is is: {}'.format(host1))
        log.debug('host2 is is: {}'.format(host2))

        origin_app, app_uuid = self.vip_app(self.num, self.container, self.vipnet, host1, self.vip)
        origin_app['acceptedResourceRoles'] = ['*', 'slave_public']
        proxy_app, _ = self.vip_app(self.num, self.container, self.proxynet, host2, None)
        proxy_app['acceptedResourceRoles'] = ['*', 'slave_public']

        returned_uuid = None
        with contextlib.ExitStack() as stack:
            stack.enter_context(dcos_api_session.marathon.deploy_and_cleanup(origin_app, timeout=timeout))
            sp = stack.enter_context(dcos_api_session.marathon.deploy_and_cleanup(proxy_app, timeout=timeout))
            proxy_host = sp[0].host
            proxy_port = sp[0].port
            if proxy_port == 0 and sp[0].ip is not None:
                proxy_port = backend_port_st + self.num
                proxy_host = sp[0].ip
            log.debug('proxy endpoints are {}'.format(sp))
            cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}/test_uuid'.format(self.vipaddr)
            returned_uuid = ensure_routable(cmd, proxy_host, proxy_port)
            log.debug('returned_uuid is: {}'.format(returned_uuid))
        assert returned_uuid is not None
        assert returned_uuid['test_uuid'] == app_uuid
        self.log('PASSED')


class ProxyPod(Enum):
    # NoPod = 0
    ItsOwnPod = 1
    SamePodAsVip = 2


class PodTest():
    def __init__(self, num: int, proxy_pod: ProxyPod, proxy_net: str,
                 vip_net: str, is_named: bool, notes: str='') -> None:
        self.num = num
        self.proxy_pod = proxy_pod
        self.proxy_net = proxy_net
        self.vip_net = vip_net
        self.is_named = is_named
        self.notes = notes
        self.port = vip_port_base + num
        self.proxy_ip = '1.1.2.{}'.format(num)
        self.proxy_vip = '{}:{}'.format(self.proxy_ip, self.port)
        self.vip = '1.1.1.{}:{}'.format(num, self.port)
        self.uri = self.vip
        if self.is_named:
            self.vip = '/vippodtest{}:{}'.format(num, self.port)
            self.uri = 'vippodtest{}.marathon.l4lb.thisdcos.directory:{}'.format(num, self.port)

    def pod_app(self):
        proxy = None
        app, guid = self.create_pod_app(self.vip_net)
        if self.proxy_pod == ProxyPod.SamePodAsVip:
            assert self.proxy_net == self.vip_net
        if self.proxy_pod == ProxyPod.ItsOwnPod:
            # recurse to create a proxy pod
            proxy, _ = self.create_pod_app(self.proxy_net)
            # delete the proxy from the vip app
            del app['containers'][0]
            # delete the vip from the proxy app
            del proxy['containers'][1]
        self.log(app)
        self.log(proxy)
        return app, guid, proxy

    def create_pod_app(self, network):
        guid = uuid.uuid4().hex
        test_id = '/vippodtest/integration-test-{}'.format(guid)
        app = {
            'id': test_id,
            'acceptedResourceRoles': ['*', 'slave_public'],
            'containers': [{
                'name': 'proxyapp{}'.format(guid),
                'resources': {
                    'cpus': 0.01,
                    'mem': 8
                },
                'image': {
                    'kind': 'DOCKER',
                    'id': 'debian:jessie'
                },
                'exec': {
                    'command': {
                        'shell': '/opt/mesosphere/bin/dcos-shell python /opt/mesosphere/active/dcos-integration-test'
                                 '/util/python_test_server.py $ENDPOINT_PROXYAPP'
                    }
                },
                'volumeMounts': [{
                    'name': 'opt',
                    'mountPath': '/opt/mesosphere'
                }],
                'endpoints': [{
                    'name': 'proxyapp',
                    'protocol': ['tcp'],
                    'hostPort': 0,
                    'labels': {'VIP_0': self.proxy_vip}
                }],
                'environment': {
                    'DCOS_TEST_UUID': 'proxy{}'.format(guid)
                }
            }, {
                'name': 'vipapp{}'.format(guid),
                'resources': {
                    'cpus': 0.01,
                    'mem': 8
                },
                'image': {
                    'kind': 'DOCKER',
                    'id': 'debian:jessie'
                },
                'exec': {
                    'command': {
                        'shell': '/opt/mesosphere/bin/dcos-shell python /opt/mesosphere/active/dcos-integration-test'
                                 '/util/python_test_server.py $ENDPOINT_VIPAPP'
                    }
                },
                'volumeMounts': [{
                    'name': 'opt',
                    'mountPath': '/opt/mesosphere'
                }],
                'endpoints': [{
                    'name': 'vipapp',
                    'protocol': ['tcp'],
                    'hostPort': 0,
                    'labels': {'VIP_0': self.vip}
                }],
                'environment': {
                    'DCOS_TEST_UUID': guid
                }
            }],
            'networks': [{'mode': 'host'}],
            'volumes': [{
                'host': '/opt/mesosphere',
                'name': 'opt'
            }]
        }
        if network == 'USER':
            app['networks'] = [{'mode': 'container',
                                'name': 'dcos'}]
        if self.proxy_net == 'USER':
            app['containers'][0]['endpoints'][0]['containerPort'] = 9000

        if self.vip_net == 'USER':
            app['containers'][1]['endpoints'][0]['containerPort'] = 9001

        return app, guid

    def __str__(self):
        s = 'PodTest(num={}, proxy_pod={}, proxy_net={}, vip_net={}, is_named={}): {}'
        s = s.format(self.num, self.proxy_pod, self.proxy_net,
                     self.vip_net, self.is_named, self.notes)
        return s

    def log(self, s, lvl=logging.DEBUG):
        m = 'VIP_TEST {} {}'.format(s, self)
        log.log(lvl, m)

    def run(self, dcos_api_session):
        self.log('START')
        origin_app, app_uuid, proxy_app = self.pod_app()
        returned_uuid = None
        with contextlib.ExitStack() as stack:
            stack.enter_context(dcos_api_session.marathon.deploy_pod_and_cleanup(origin_app, timeout=timeout))
            if proxy_app is not None:
                stack.enter_context(dcos_api_session.marathon.deploy_pod_and_cleanup(proxy_app, timeout=timeout))
            cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}/test_uuid'.format(self.uri)
            returned_uuid = ensure_routable(cmd, self.proxy_ip, self.port)
            log.debug('returned_uuid is: {}'.format(returned_uuid))
        assert returned_uuid is not None
        assert returned_uuid['test_uuid'] == app_uuid
        self.log('PASSED')


@pytest.fixture
def reduce_logging():
    marathon_log_lvl = logging.getLogger('test_util.marathon').getEffectiveLevel()
    helpers_log_lvl = logging.getLogger('test_util.helpers').getEffectiveLevel()
    # gotta go up to warning to mute it as its currently at info
    logging.getLogger('test_util.marathon').setLevel(logging.WARNING)
    logging.getLogger('test_util.helpers').setLevel(logging.WARNING)
    yield
    logging.getLogger('test_util.marathon').setLevel(marathon_log_lvl)
    logging.getLogger('test_util.helpers').setLevel(helpers_log_lvl)


@pytest.mark.skipif(not lb_enabled(), reason='Load Balancer disabled')
def test_vip(dcos_api_session, reduce_logging):
    '''Test every permutation of VIP
    '''
    # tests
    # UCR doesn't support BRIDGE mode
    permutations = [[container, is_named, same_host, vip_net, proxy_net]
                    for container in ['NONE', 'UCR', 'DOCKER']
                    for is_named in [True, False]
                    for same_host in [True, False]
                    for vip_net in ['USER', 'BRIDGE', 'HOST']
                    for proxy_net in ['USER', 'BRIDGE', 'HOST']]
    tests = [VipTest(i + 1, container, is_named, same_host, vip_net, proxy_net)
             for i, [container, is_named, same_host, vip_net, proxy_net] in enumerate(permutations)]
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=maxthreads)
    # deque is thread safe
    # tests that didn't finish running
    failed_tests = deque()
    # test that ran successfully
    passed_tests = deque()
    # tests that were skipped because cluster configuration cannot support them
    skipped_tests = deque()
    # skip certain tests
    for vip_test in tests:
        if vip_test.container == 'UCR' or vip_test.container == 'NONE':
            if vip_test.vipnet == 'BRIDGE' or vip_test.proxynet == 'BRIDGE':
                vip_test.notes = 'bridge networks are not supported by mesos runtime'
                skipped_tests.append(vip_test)
                continue
        if not vip_test.samehost and len(dcos_api_session.all_slaves) == 1:
            vip_test.notes = 'needs more then 1 agent to run'
            skipped_tests.append(vip_test)
            continue
        failed_tests.append(vip_test)
    permutations = [[proxy_pod, proxy_net, vip_net, is_named]
                    for proxy_pod in [ProxyPod.ItsOwnPod, ProxyPod.SamePodAsVip]
                    for proxy_net in ['HOST', 'USER']
                    for vip_net in ['HOST', 'USER']
                    for is_named in [True, False]]
    pods = [PodTest(i + len(tests), proxy_pod, proxy_net, vip_net, is_named)
            for i, [proxy_pod, proxy_net, vip_net, is_named] in enumerate(permutations)]
    for pod_test in pods:
        if pod_test.proxy_pod == ProxyPod.SamePodAsVip and pod_test.vip_net != pod_test.proxy_net:
            pod_test.notes = "Invalid configuration, pods only support single network for entire pod"
            skipped_tests.append(pod_test)
            continue
        failed_tests.append(pod_test)

    def run(test):
        test.run(dcos_api_session)
        failed_tests.remove(test)
        passed_tests.append(test)

    tasks = [executor.submit(run, t) for t in failed_tests]
    for t in concurrent.futures.as_completed(tasks):
        try:
            t.result()
        except Exception as exc:
            # just log the exception, each failed test is recorded in the `failed_tests` array
            log.info('vip_test generated an exception: {}'.format(exc))
    [r.log('PASSED', lvl=logging.DEBUG) for r in passed_tests]
    [r.log('SKIPPED', lvl=logging.DEBUG) for r in skipped_tests]
    [r.log('FAILED', lvl=logging.INFO) for r in failed_tests]
    log.debug('VIP_TEST num agents: {}'.format(len(dcos_api_session.all_slaves)))
    log.info('VIP_TEST passed {} skipped {} failed {}'.format(len(passed_tests), len(skipped_tests), len(failed_tests)))
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
    # Launch the test_server in ip-per-container mode
    app_definition, test_uuid = get_test_app_in_docker(ip_per_container=True)

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
    log.debug('geturl {} -> {}'.format(url, r))
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
