

import contextlib
import enum
import json
import logging
import subprocess
import threading
import time
import uuid
from collections import deque

import pytest
import requests
import retrying
import test_helpers

from dcos_test_utils import marathon
from dcos_test_utils.helpers import assert_response_ok

__maintainer__ = 'urbanserj'
__contact__ = 'dcos-networking@mesosphere.io'

log = logging.getLogger(__name__)

GLOBAL_PORT_POOL = iter(range(10000, 32000))


class Container(enum.Enum):
    POD = 'POD'


class MarathonApp:
    def __init__(self, container, network, host, vip=None, ipv6=False, app_name_fmt=None):
        args = {
            'app_name_fmt': app_name_fmt,
            'network': network,
            'host_port': unused_port(),
            'host_constraint': host,
            'vip': vip,
            'container_type': container,
            'healthcheck_protocol': marathon.Healthcheck.MESOS_HTTP
        }
        if network == marathon.Network.USER:
            args['container_port'] = unused_port()
            if ipv6:
                args['network_name'] = 'dcos6'
            if vip is not None:
                del args['host_port']
        self.app, self.uuid = test_helpers.marathon_test_app(**args)
        # allow this app to run on public slaves
        self.app['acceptedResourceRoles'] = ['*', 'slave_public']
        self.id = self.app['id']

    def __str__(self):
        return str(self.app)

    def deploy(self, dcos_api_session):
        return dcos_api_session.marathon.post('/v2/apps', json=self.app).raise_for_status()

    @retrying.retry(
        wait_fixed=5000,
        stop_max_delay=20 * 60 * 1000)
    def wait(self, dcos_api_session):
        r = dcos_api_session.marathon.get('/v2/apps/{}'.format(self.id))
        assert_response_ok(r)

        self._info = r.json()
        assert self._info['app']['tasksHealthy'] == self.app['instances']

    def info(self, dcos_api_session):
        try:
            if self._info['app']['tasksHealthy'] != self.app['instances']:
                raise Exception("Number of Healthy Tasks not equal to number of instances.")
        except Exception:
            self.wait(dcos_api_session)
        return self._info

    def hostport(self, dcos_api_session):
        info = self.info(dcos_api_session)
        task = info['app']['tasks'][0]
        if 'networks' in self.app and \
                self.app['networks'][0]['mode'] == 'container' and \
                self.app['networks'][0]['name'] != 'dcos6':
            host = task['ipAddresses'][0]['ipAddress']
            port = self.app['container']['portMappings'][0]['containerPort']
        else:
            host = task['host']
            port = task['ports'][0]
        return host, port

    def purge(self, dcos_api_session):
        return dcos_api_session.marathon.delete('/v2/apps/{}'.format(self.id))


class MarathonPod:
    def __init__(self, network, host, vip=None, pod_name_fmt='/integration-test-{}'):
        self._network = network
        container_port = 0
        if network is not marathon.Network.HOST:
            container_port = unused_port()
        # ENDPOINT_TEST will be computed from the `endpoints` definition. See [1], [2]
        # [1] https://dcos.io/docs/1.10/deploying-services/pods/technical-overview/#environment-variables
        # [2] https://github.com/mesosphere/marathon/blob/v1.5.0/
        #     src/main/scala/mesosphere/mesos/TaskGroupBuilder.scala#L420-L443
        port = '$ENDPOINT_TEST' if network == marathon.Network.HOST else container_port
        self.uuid = uuid.uuid4().hex
        self.id = pod_name_fmt.format(self.uuid)
        self.app = {
            'id': self.id,
            'scheduling': {'placement': {'acceptedResourceRoles': ['*', 'slave_public']}},
            'containers': [{
                'name': 'app-{}'.format(self.uuid),
                'resources': {'cpus': 0.01, 'mem': 32},
                'image': {'kind': 'DOCKER', 'id': 'debian:jessie'},
                'exec': {'command': {
                    'shell': '/opt/mesosphere/bin/dcos-shell python '
                             '/opt/mesosphere/active/dcos-integration-test/util/python_test_server.py '
                             '{}'.format(port)
                }},
                'volumeMounts': [{'name': 'opt', 'mountPath': '/opt/mesosphere'}],
                'endpoints': [{'name': 'test', 'protocol': ['tcp'], 'hostPort': unused_port()}],
                'environment': {'DCOS_TEST_UUID': self.uuid, 'HOME': '/'}
            }],
            'networks': [{'mode': 'host'}],
            'volumes': [{'name': 'opt', 'host': '/opt/mesosphere'}]
        }
        if host is not None:
            self.app['scheduling']['placement']['constraints'] = \
                [{'fieldName': 'hostname', 'operator': 'CLUSTER', 'value': host}]
        if vip is not None:
            self.app['containers'][0]['endpoints'][0]['labels'] = \
                {'VIP_0': vip}
        if network == marathon.Network.USER:
            del self.app['containers'][0]['endpoints'][0]['hostPort']
            self.app['containers'][0]['endpoints'][0]['containerPort'] = container_port
            self.app['networks'] = [{'name': 'dcos', 'mode': 'container'}]
        elif network == marathon.Network.BRIDGE:
            self.app['containers'][0]['endpoints'][0]['containerPort'] = container_port
            self.app['networks'] = [{'mode': 'container/bridge'}]

    def __str__(self):
        return str(self.app)

    def deploy(self, dcos_api_session):
        return dcos_api_session.marathon.post('/v2/pods', json=self.app).raise_for_status()

    @retrying.retry(
        wait_fixed=5000,
        stop_max_delay=20 * 60 * 1000,
        retry_on_result=lambda res: res is False)
    def wait(self, dcos_api_session):
        r = dcos_api_session.marathon.get('/v2/pods/{}::status'.format(self.id))
        assert_response_ok(r)

        self._info = r.json()
        error_msg = 'Status was {}: {}'.format(self._info['status'], self._info.get('message', 'no message'))
        assert self._info['status'] == 'STABLE', error_msg

    def info(self, dcos_api_session):
        try:
            if self._info['status'] != 'STABLE':
                raise Exception("The status information is not Stable!")
        except Exception:
            self.wait(dcos_api_session)
        return self._info

    def hostport(self, dcos_api_session):
        info = self.info(dcos_api_session)
        if self._network == marathon.Network.USER:
            host = info['instances'][0]['networks'][0]['addresses'][0]
            port = self.app['containers'][0]['endpoints'][0]['containerPort']
        else:
            host = info['instances'][0]['agentHostname']
            port = info['instances'][0]['containers'][0]['endpoints'][0]['allocatedHostPort']
        return host, port

    def purge(self, dcos_api_session):
        return dcos_api_session.marathon.delete('/v2/pods/{}'.format(self.id))


def unused_port():
    global GLOBAL_PORT_POOL
    return next(GLOBAL_PORT_POOL)


def lb_enabled():
    expanded_config = test_helpers.get_expanded_config()
    return expanded_config['enable_lb'] == 'true'


@retrying.retry(wait_fixed=2000,
                stop_max_delay=5 * 60 * 1000,
                retry_on_result=lambda ret: ret is None)
def ensure_routable(cmd, host, port):
    proxy_uri = 'http://{}:{}/run_cmd'.format(host, port)
    log.info('Sending {} data: {}'.format(proxy_uri, cmd))
    response = requests.post(proxy_uri, data=cmd, timeout=5).json()
    log.info('Requests Response: {}'.format(repr(response)))
    if response['status'] != 0:
        return None
    return json.loads(response['output'])


def generate_vip_app_permutations():
    """ Generate all possible network interface permutations for applying vips
    """
    containers = list(marathon.Container) + [Container.POD]
    return [(container, vip_net, proxy_net)
            for container in containers
            for vip_net in list(marathon.Network)
            for proxy_net in list(marathon.Network)]


def workload_test(dcos_api_session, container, app_net, proxy_net, ipv6, same_host):
    (vip, hosts, cmd, origin_app, proxy_app) = \
        vip_workload_test(dcos_api_session, container,
                          app_net, proxy_net, ipv6, True, same_host)
    return (hosts, origin_app, proxy_app)


@pytest.mark.first
def test_docker_image_availablity():
    assert test_helpers.docker_pull_image("debian:jessie"), "docker pull failed for image used in the test"


@pytest.mark.xfailflake(
    jira='DCOS-19790',
    reason='test_ipv6 fails with 0 tasks healthy',
    since='2019-03-15'
)
@pytest.mark.slow
@pytest.mark.parametrize('same_host', [True, False])
def test_ipv6(dcos_api_session, same_host):
    ''' Testing autoip, containerip and *.mesos FQDN on ipv6 overlay network '''
    (hosts, origin_app, proxy_app) = \
        workload_test(dcos_api_session, marathon.Container.DOCKER,
                      marathon.Network.USER, marathon.Network.USER, True, same_host)
    log.info('Starting apps :: Hosts: {}'.format(hosts))
    log.info("Origin app: {}".format(origin_app))
    origin_app.deploy(dcos_api_session)
    log.info("Proxy app: {}".format(proxy_app))
    proxy_app.deploy(dcos_api_session)
    origin_app.wait(dcos_api_session)
    proxy_app.wait(dcos_api_session)
    log.info('Apps are ready')
    origin_app_info = origin_app.info(dcos_api_session)
    origin_port = origin_app_info['app']['container']['portMappings'][0]['containerPort']
    proxy_host, proxy_port = proxy_app.hostport(dcos_api_session)
    dns_name = '-'.join(reversed(origin_app.id.split('/')[1:]))
    try:
        zones = ["marathon.autoip.dcos.thisdcos.directory",
                 "marathon.containerip.dcos.thisdcos.directory",
                 "marathon.mesos"]
        for zone in zones:
            cmd = '{} --ipv6 http://{}/test_uuid'.format(
                '/opt/mesosphere/bin/curl -s -f -m 5',
                '{}.{}:{}'.format(dns_name, zone, origin_port))
            log.info("Remote command: {}".format(cmd))
            ensure_routable(cmd, proxy_host, proxy_port)['test_uuid'] == origin_app.uuid
    finally:
        log.info('Purging application: {}'.format(origin_app.id))
        origin_app.purge(dcos_api_session)
        log.info('Purging application: {}'.format(proxy_app.id))
        proxy_app.purge(dcos_api_session)


@pytest.mark.xfailflake(
    jira='DCOS-50427',
    reason='fails with read timeout.',
    since='2019-03-19'
)
@pytest.mark.slow
def test_vip_ipv6(dcos_api_session):
    return test_vip(dcos_api_session, marathon.Container.DOCKER,
                    marathon.Network.USER, marathon.Network.USER, ipv6=True)


@pytest.mark.slow
@pytest.mark.parametrize(
    'container,vip_net,proxy_net',
    generate_vip_app_permutations())
def test_vip(dcos_api_session,
             container: marathon.Container,
             vip_net: marathon.Network,
             proxy_net: marathon.Network,
             ipv6: bool=False):
    '''Test VIPs between the following source and destination configurations:
        * containers: DOCKER, UCR and NONE
        * networks: USER, BRIDGE, HOST
        * agents: source and destnations on same agent or different agents
        * vips: named and unnamed vip

    Origin app will be deployed to the cluster with a VIP. Proxy app will be
    deployed either to the same host or elsewhere. Finally, a thread will be
    started on localhost (which should be a master) to submit a command to the
    proxy container that will ping the origin container VIP and then assert
    that the expected origin app UUID was returned
    '''
    if not lb_enabled():
        pytest.skip('Load Balancer disabled')

    errors = []
    tests = setup_vip_workload_tests(dcos_api_session, container, vip_net, proxy_net, ipv6)
    for vip, hosts, cmd, origin_app, proxy_app in tests:
        log.info("Testing :: VIP: {}, Hosts: {}".format(vip, hosts))
        log.info("Remote command: {}".format(cmd))
        proxy_host, proxy_port = proxy_app.hostport(dcos_api_session)
        try:
            ensure_routable(cmd, proxy_host, proxy_port)['test_uuid'] == origin_app.uuid
        except Exception as e:
            log.error('Exception: {}'.format(e))
            errors.append(e)
        finally:
            log.info('Purging application: {}'.format(origin_app.id))
            origin_app.purge(dcos_api_session)
            log.info('Purging application: {}'.format(proxy_app.id))
            proxy_app.purge(dcos_api_session)
    assert not errors


def setup_vip_workload_tests(dcos_api_session, container, vip_net, proxy_net, ipv6):
    same_hosts = [True, False] if len(dcos_api_session.all_slaves) > 1 else [True]
    tests = [vip_workload_test(dcos_api_session, container, vip_net, proxy_net, ipv6, named_vip, same_host)
             for named_vip in [True, False]
             for same_host in same_hosts]
    for vip, hosts, cmd, origin_app, proxy_app in tests:
        # We do not need the service endpoints because we have deterministically assigned them
        log.info('Starting apps :: VIP: {}, Hosts: {}'.format(vip, hosts))
        log.info("Origin app: {}".format(origin_app))
        origin_app.deploy(dcos_api_session)
        log.info("Proxy app: {}".format(proxy_app))
        proxy_app.deploy(dcos_api_session)
    for vip, hosts, cmd, origin_app, proxy_app in tests:
        log.info("Deploying apps :: VIP: {}, Hosts: {}".format(vip, hosts))
        log.info('Deploying origin app: {}'.format(origin_app.id))
        origin_app.wait(dcos_api_session)
        log.info('Deploying proxy app: {}'.format(proxy_app.id))
        proxy_app.wait(dcos_api_session)
        log.info('Apps are ready')
    return tests


def vip_workload_test(dcos_api_session, container, vip_net, proxy_net, ipv6, named_vip, same_host):
    slaves = dcos_api_session.slaves + dcos_api_session.public_slaves
    vip_port = unused_port()
    origin_host = slaves[0]
    proxy_host = slaves[0] if same_host else slaves[1]
    if named_vip:
        vip = '/namedvip:{}'.format(vip_port)
        vipaddr = 'namedvip.marathon.l4lb.thisdcos.directory:{}'.format(vip_port)
    elif ipv6:
        vip = 'fd01:c::1:{}'.format(vip_port)
        vipaddr = '[fd01:c::1]:{}'.format(vip_port)
    else:
        vip = '1.1.1.7:{}'.format(vip_port)
        vipaddr = vip
    cmd = '{} {} http://{}/test_uuid'.format(
        '/opt/mesosphere/bin/curl -s -f -m 5',
        '--ipv6' if ipv6 else '--ipv4',
        vipaddr)
    path_id = '/integration-tests/{}-{}-{}'.format(
        enum2str(container),
        net2str(vip_net, ipv6),
        net2str(proxy_net, ipv6))
    test_case_id = '{}-{}'.format(
        'named' if named_vip else 'vip',
        'local' if same_host else 'remote')
    # NOTE: DNS label can't be longer than 63 bytes
    origin_fmt = '{}/app-{}'.format(path_id, test_case_id)
    origin_fmt = origin_fmt + '-{{:.{}}}'.format(63 - len(origin_fmt))
    proxy_fmt = '{}/proxy-{}'.format(path_id, test_case_id)
    proxy_fmt = proxy_fmt + '-{{:.{}}}'.format(63 - len(proxy_fmt))
    if container == Container.POD:
        origin_app = MarathonPod(vip_net, origin_host, vip, pod_name_fmt=origin_fmt)
        proxy_app = MarathonPod(proxy_net, proxy_host, pod_name_fmt=proxy_fmt)
    else:
        origin_app = MarathonApp(container, vip_net, origin_host, vip, ipv6=ipv6, app_name_fmt=origin_fmt)
        proxy_app = MarathonApp(container, proxy_net, proxy_host, ipv6=ipv6, app_name_fmt=proxy_fmt)
    hosts = list(set([origin_host, proxy_host]))
    return (vip, hosts, cmd, origin_app, proxy_app)


@pytest.mark.xfailflake(
    jira='DCOS-19790',
    reason='test_if_overlay_ok fails with STATUS_FAILED',
    since='2019-03-15'
)
@retrying.retry(wait_fixed=2000,
                stop_max_delay=120 * 1000,
                retry_on_exception=lambda x: True)
def test_if_overlay_ok(dcos_api_session):
    def _check_overlay(hostname, port):
        overlays = dcos_api_session.get('/overlay-agent/overlay', host=hostname, port=port).json()['overlays']
        assert len(overlays) > 0
        for overlay in overlays:
            assert overlay['state']['status'] == 'STATUS_OK'

    for master in dcos_api_session.masters:
        _check_overlay(master, 5050)
    for slave in dcos_api_session.all_slaves:
        _check_overlay(slave, 5051)


def test_if_dcos_l4lb_disabled(dcos_api_session):
    '''Test to make sure dcos_l4lb is disabled'''
    if lb_enabled():
        pytest.skip('Load Balancer enabled')
    data = subprocess.check_output(['/usr/bin/env', 'ip', 'rule'])
    # dcos-net creates this ip rule: `9999: from 9.0.0.0/8 lookup 42`
    # We check it doesn't exist
    assert str(data).find('9999') == -1


def test_ip_per_container(dcos_api_session):
    '''Test if we are able to connect to a task with ip-per-container mode
    '''
    # Launch the test_server in ip-per-container mode (user network)
    if len(dcos_api_session.slaves) < 2:
        pytest.skip("IP Per Container tests require 2 private agents to work")

    app_definition, test_uuid = test_helpers.marathon_test_app(
        healthcheck_protocol=marathon.Healthcheck.MESOS_HTTP,
        container_type=marathon.Container.DOCKER,
        network=marathon.Network.USER,
        host_port=9080)

    app_definition['instances'] = 2
    app_definition['constraints'] = [['hostname', 'UNIQUE']]

    with dcos_api_session.marathon.deploy_and_cleanup(app_definition, check_health=True):
        service_points = dcos_api_session.marathon.get_app_service_endpoints(app_definition['id'])
        app_port = app_definition['container']['portMappings'][0]['containerPort']
        cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}:{}/ping'.format(service_points[1].ip, app_port)
        ensure_routable(cmd, service_points[0].host, service_points[0].port)


@pytest.mark.parametrize('networking_mode', list(marathon.Network))
@pytest.mark.parametrize('host_port', [9999, 0])
def test_app_networking_mode_with_defined_container_port(dcos_api_session, networking_mode, host_port):
    """
    The Admin Router can proxy a request on the `/service/[app]`
    endpoint to an application running in a container in different networking
    modes with manually or automatically assigned host port on which is
    the application HTTP endpoint exposed.

    Networking modes are testing following configurations:
    - host
    - container
    - container/bridge

    https://mesosphere.github.io/marathon/docs/networking.html#networking-modes
    """
    app_definition, test_uuid = test_helpers.marathon_test_app(
        healthcheck_protocol=marathon.Healthcheck.MESOS_HTTP,
        container_type=marathon.Container.DOCKER,
        network=networking_mode,
        host_port=host_port)

    dcos_service_name = uuid.uuid4().hex

    app_definition['labels'] = {
        'DCOS_SERVICE_NAME': dcos_service_name,
        'DCOS_SERVICE_PORT_INDEX': '0',
        'DCOS_SERVICE_SCHEME': 'http',
    }

    #  Arbitrary buffer time, accounting for propagation/processing delay.
    buffer_time = 5

    #  Cache refresh in Adminrouter takes 30 seconds at most.
    #  CACHE_POLL_PERIOD=25s + valid=5s Nginx resolver DNS entry TTL
    #  https://github.com/dcos/dcos/blob/cb9105ee537cc44cbe63cc7c53b3b01b764703a0/
    #  packages/adminrouter/extra/src/includes/http/master.conf#L21
    adminrouter_default_refresh = 25 + 5 + buffer_time
    app_id = app_definition['id']
    app_instances = app_definition['instances']
    app_definition['constraints'] = [['hostname', 'UNIQUE']]

    # For the routing check to work, two conditions must be true:
    #
    # 1. The application must be deployed, so that `/ping` responds with 200.
    # 2. The Admin Router routing layer must not be using an outdated
    #    version of the Nginx resolver cache.
    #
    # We therefore wait until these conditions have certainly been met.
    # We wait for the Admin Router cache refresh first so that there is
    # unlikely to be much double-waiting. That is, we do not want to be waiting
    # for the cache to refresh when it already refreshed while we were waiting
    # for the app to become healthy.
    with dcos_api_session.marathon.deploy_and_cleanup(app_definition, check_health=False):
        time.sleep(adminrouter_default_refresh)
        dcos_api_session.marathon.wait_for_app_deployment(
            app_id=app_id,
            app_instances=app_instances,
            check_health=False,
            ignore_failed_tasks=False,
            timeout=1200,
        )
        r = dcos_api_session.get('/service/' + dcos_service_name + '/ping')
        assert r.status_code == 200
        assert 'pong' in r.json()


@retrying.retry(wait_fixed=2000,
                stop_max_delay=100 * 2000,
                retry_on_exception=lambda x: True)
def geturl(url):
    rs = requests.get(url)
    assert rs.status_code == 200
    r = rs.json()
    log.info('geturl {} -> {}'.format(url, r))
    return r


def test_l4lb(dcos_api_session):
    '''Test l4lb is load balancing between all the backends
       * create 5 apps using the same VIP
       * get uuid from the VIP in parallel from many threads
       * verify that 5 uuids have been returned
       * only testing if all 5 are hit at least once
    '''
    if not lb_enabled():
        pytest.skip('Load Balancer disabled')
    numapps = 5
    numthreads = numapps * 4
    apps = []
    rvs = deque()
    backends = []
    dnsname = 'l4lbtest.marathon.l4lb.thisdcos.directory:5000'
    with contextlib.ExitStack() as stack:
        for _ in range(numapps):
            origin_app, origin_uuid = \
                test_helpers.marathon_test_app(
                    healthcheck_protocol=marathon.Healthcheck.MESOS_HTTP)
            # same vip for all the apps
            origin_app['portDefinitions'][0]['labels'] = {'VIP_0': '/l4lbtest:5000'}
            apps.append(origin_app)
            stack.enter_context(dcos_api_session.marathon.deploy_and_cleanup(origin_app))
            sp = dcos_api_session.marathon.get_app_service_endpoints(origin_app['id'])
            backends.append({'port': sp[0].port, 'ip': sp[0].host})
            # make sure that the service point responds
            geturl('http://{}:{}/ping'.format(sp[0].host, sp[0].port))
            # make sure that the VIP is responding too
            geturl('http://{}/ping'.format(dnsname))
        vips = geturl("http://localhost:62080/v1/vips")
        [vip] = [vip for vip in vips if vip['vip'] == dnsname and vip['protocol'] == 'tcp']
        for backend in vip['backend']:
            backends.remove(backend)
        assert backends == []

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


def test_dcos_cni_l4lb(dcos_api_session):
    '''
    This tests the `dcos - l4lb` CNI plugins:
        https: // github.com / dcos / dcos - cni / tree / master / cmd / l4lb

    The `dcos-l4lb` CNI plugins allows containers running on networks that don't
    necessarily have routes to spartan interfaces and minuteman VIPs to consume DNS
    service from spartan and layer-4 load-balancing services from minuteman by
    injecting spartan and minuteman services into the container's network
    namespace. You can read more about the motivation for this CNI plugin and type
    of problems it solves in this design doc:

    https://docs.google.com/document/d/1xxvkFknC56hF-EcDmZ9tzKsGiZdGKBUPfrPKYs85j1k/edit?usp=sharing

    In order to test `dcos-l4lb` CNI plugin we emulate a virtual network that
    lacks routes for spartan interface and minuteman VIPs. In this test, we
    first install a virtual network called `spartan-net` on one of the agents.
    The `spartan-net` is a CNI network that is a simple BRIDGE network with the
    caveat that it doesn't have any default routes. `spartan-net` has routes
    only for the agent network. In other words it doesn't have any routes
    towards the spartan-interfaces or minuteman VIPs.

    We then run a server (our python ping-pong server) on the DC/OS overlay.
    Finally to test that the `dcos-l4lb` plugin, which is also part of
    `spartan-net` is able to inject the Minuteman and Spartan services into the
    contianer's netns, we start a client on the `spartan-net` and try to `curl` the
    `ping-pong` server using its VIP. Without the Minuteman and Spartan services
    injected in the container's netns the expectation would be that this `curl`
    would fail, with a successful `curl` execution on the VIP allowing the
    test-case to PASS.
    '''
    if not lb_enabled():
        pytest.skip('Load Balancer disabled')

    expanded_config = test_helpers.get_expanded_config()
    if expanded_config.get('security') == 'strict':
        pytest.skip('Cannot setup CNI config with EE strict mode enabled')

    # CNI configuration of `spartan-net`.
    spartan_net = {
        'cniVersion': '0.2.0',
        'name': 'spartan-net',
        'type': 'dcos-l4lb',
        'delegate': {
            'type': 'mesos-cni-port-mapper',
            'excludeDevices': ['sprt-cni0'],
            'chain': 'spartan-net',
            'delegate': {
                'type': 'bridge',
                'bridge': 'sprt-cni0',
                'ipMasq': True,
                'isGateway': True,
                'ipam': {
                    'type': 'host-local',
                    'subnet': '192.168.250.0/24',
                    'routes': [
                     # Reachability to DC/OS overlay.
                     {'dst': '9.0.0.0/8'},
                     # Reachability to all private address subnet. We need
                     # this reachability since different cloud providers use
                     # different private address spaces to launch tenant
                     # networks.
                     {'dst': '10.0.0.0/8'},
                     {'dst': '172.16.0.0/12'},
                     {'dst': '192.168.0.0/16'}
                    ]
                }
            }
        }
    }

    log.info("spartan-net config:{}".format(json.dumps(spartan_net)))

    # Application to deploy CNI configuration.
    cni_config_app, config_uuid = test_helpers.marathon_test_app()

    # Override the default test app command with a command to write the CNI
    # configuration.
    #
    # NOTE: We add the sleep at the end of this command so that the task stays
    # alive for the test harness to make sure that the task got deployed.
    # Ideally we should be able to deploy one of tasks using the test harness
    # but that doesn't seem to be the case here.
    cni_config_app['cmd'] = 'echo \'{}\' > /opt/mesosphere/etc/dcos/network/cni/spartan.cni && sleep 10000'.format(
        json.dumps(spartan_net))
    del cni_config_app['healthChecks']

    log.info("App for setting CNI config: {}".format(json.dumps(cni_config_app)))

    try:
        dcos_api_session.marathon.deploy_app(cni_config_app, check_health=False)
    except Exception as ex:
        raise AssertionError("Couldn't install CNI config for `spartan-net`".format(json.dumps(cni_config_app))) from ex

    # Get the host on which the `spartan-net` was installed.
    cni_config_app_service = None
    try:
        cni_config_app_service = dcos_api_session.marathon.get_app_service_endpoints(cni_config_app['id'])
    except Exception as ex:
        raise AssertionError("Couldn't retrieve the host on which `spartan-net` was installed.") from ex

    # We only have one instance of `cni_config_app_service`.
    spartan_net_host = cni_config_app_service[0].host

    # Launch the test-app on DC/OS overlay, with a VIP.
    server_vip_port = unused_port()
    server_vip = '/spartanvip:{}'.format(server_vip_port)
    server_vip_addr = 'spartanvip.marathon.l4lb.thisdcos.directory:{}'.format(server_vip_port)

    # Launch the test_server in ip-per-container mode (user network)
    server, test_uuid = test_helpers.marathon_test_app(
        container_type=marathon.Container.MESOS,
        healthcheck_protocol=marathon.Healthcheck.MESOS_HTTP,
        network=marathon.Network.USER,
        host_port=9080,
        vip=server_vip)

    # Launch the server on the DC/OS overlay
    log.info("Launching server with VIP:{} on network {}".format(server_vip_addr, server['networks'][0]['name']))

    try:
        dcos_api_session.marathon.deploy_app(server, check_health=False)
    except Exception as ex:
        raise AssertionError(
            "Couldn't launch server on 'dcos':{}".format(server['networks'][0]['name'])) from ex

    # Get the client app on the 'spartan-net' network.
    client_port = 9081
    client, test_uuid = test_helpers.marathon_test_app(
        container_type=marathon.Container.MESOS,
        healthcheck_protocol=marathon.Healthcheck.MESOS_HTTP,
        network=marathon.Network.USER,
        host_port=client_port,
        container_port=client_port,
        vip=server_vip,
        host_constraint=spartan_net_host,
        network_name='spartan-net')

    try:
        dcos_api_session.marathon.deploy_app(client, check_health=False)
    except Exception as ex:
        raise AssertionError("Couldn't launch client on 'spartan-net':{}".format(client)) from ex

    # Change the client command task to do a curl on the server we just deployed.
    cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}/ping'.format(server_vip_addr)

    try:
        response = ensure_routable(cmd, spartan_net_host, client_port)
        log.info("Received a response from {}: {}".format(server_vip_addr, response))
    except Exception as ex:
        raise AssertionError("Unable to query VIP: {}".format(server_vip_addr)) from ex


def enum2str(value):
    return str(value).split('.')[-1].lower()


def net2str(value, ipv6):
    return enum2str(value) if not ipv6 else 'ipv6'


@pytest.mark.xfailflake(
    jira='DCOS-47438',
    reason='test_dcos_net_cluster_identity fails',
    since='2019-03-15'
)
def test_dcos_net_cluster_identity(dcos_api_session):
    cluster_id = 'minuteman'  # default

    expanded_config = test_helpers.get_expanded_config()
    if expanded_config['dcos_net_cluster_identity'] == 'true':
        with open('/var/lib/dcos/cluster-id') as f:
            cluster_id = "'{}'".format(f.readline().rstrip())

    argv = ['sudo', '/opt/mesosphere/bin/dcos-net-env', 'eval', 'erlang:get_cookie().']
    cookie = subprocess.check_output(argv, stderr=subprocess.STDOUT).decode('utf-8').rstrip()

    assert cluster_id == cookie, "cluster_id: {}, cookie: {}".format(cluster_id, cookie)
