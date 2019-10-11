import enum
import itertools
import json
import logging
import subprocess
import time
import uuid

import pytest
import requests
import retrying
import test_helpers

from dcos_test_utils import marathon
from dcos_test_utils.helpers import assert_response_ok


__maintainer__ = 'urbanserj'
__contact__ = 'networking-team@mesosphere.io'

log = logging.getLogger(__name__)

GLOBAL_PORT_POOL = iter(range(10000, 32000))
GLOBAL_OCTET_POOL = itertools.cycle(range(254, 10, -1))

# Apply fixture(s) in this list to all tests in this module. From
# pytest docs: "Note that the assigned variable must be called pytestmark"
pytestmark = [pytest.mark.usefixtures("clean_marathon_state_function_scoped")]


class Container(enum.Enum):
    POD = 'POD'


class MarathonApp:
    def __init__(self,
                 container,
                 network,
                 host=None,
                 vip=None,
                 network_name=None,
                 app_name_fmt=None,
                 host_port=None):
        if host_port is None:
            host_port = unused_port()
        args = {
            'app_name_fmt': app_name_fmt,
            'network': network,
            'host_port': host_port,
            'vip': vip,
            'container_type': container,
            'healthcheck_protocol': marathon.Healthcheck.MESOS_HTTP,
        }
        if host is not None:
            args['host_constraint'] = host
        if network == marathon.Network.USER:
            args['container_port'] = unused_port()
            if network_name is not None:
                args['network_name'] = network_name
            if vip is not None:
                del args['host_port']
        self.app, self.uuid = test_helpers.marathon_test_app(**args)
        # allow this app to run on public slaves
        self.app['acceptedResourceRoles'] = ['*', 'slave_public']
        self.id = self.app['id']

    def __str__(self):
        return str(self.app)

    def deploy(self, dcos_api_session):
        return dcos_api_session.marathon.post(
            '/v2/apps', json=self.app).raise_for_status()

    @retrying.retry(wait_fixed=5000, stop_max_delay=20 * 60 * 1000)
    def wait(self, dcos_api_session):
        r = dcos_api_session.marathon.get('/v2/apps/{}'.format(self.id))
        assert_response_ok(r)

        self._info = r.json()
        assert self._info['app']['tasksHealthy'] == self.app['instances']

    def info(self, dcos_api_session):
        try:
            if self._info['app']['tasksHealthy'] != self.app['instances']:
                raise Exception("Number of Healthy Tasks not equal to number"
                                " of instances.")
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
    def __init__(self,
                 network,
                 host,
                 vip=None,
                 pod_name_fmt='/integration-test-{}',
                 network_name='dcos'):
        self._network = network
        container_port = 0
        if network is not marathon.Network.HOST:
            container_port = unused_port()
        # ENDPOINT_TEST will be computed from the `endpoints` definition.
        # See [1], [2]:
        # [1] https://dcos.io/docs/1.10/deploying-services/pods/technical-overview/#environment-variables # NOQA
        # [2] https://github.com/mesosphere/marathon/blob/v1.5.0/src/main/scala/mesosphere/mesos/TaskGroupBuilder.scala#L420-L443 # NOQA
        port = '$ENDPOINT_TEST' if network == marathon.Network.HOST \
            else container_port
        self.uuid = uuid.uuid4().hex
        self.id = pod_name_fmt.format(self.uuid)
        self.app = {
            'id':
            self.id,
            'scheduling': {
                'placement': {
                    'acceptedResourceRoles': ['*', 'slave_public'],
                },
            },
            'containers': [{
                'name':
                'app-{}'.format(self.uuid),
                'resources': {
                    'cpus': 0.01,
                    'mem': 32,
                },
                'image': {
                    'kind': 'DOCKER',
                    'id': 'debian:stretch-slim',
                },
                'exec': {
                    'command': {
                        'shell':
                        '/opt/mesosphere/bin/dcos-shell python '
                        '/opt/mesosphere/active/dcos-integration-test/util/python_test_server.py '  # NOQA
                        '{}'.format(port),
                    },
                },
                'volumeMounts': [{
                    'name': 'opt',
                    'mountPath': '/opt/mesosphere',
                }],
                'endpoints': [{
                    'name': 'test',
                    'protocol': ['tcp'],
                    'hostPort': unused_port(),
                }],
                'environment': {
                    'DCOS_TEST_UUID': self.uuid,
                    'HOME': '/',
                },
            }],
            'networks': [{
                'mode': 'host',
            }],
            'volumes': [{
                'name': 'opt',
                'host': '/opt/mesosphere',
            }],
        }
        if host is not None:
            self.app['scheduling']['placement']['constraints'] = \
                [{'fieldName': 'hostname',
                  'operator': 'CLUSTER',
                  'value': host}]
        if vip is not None:
            self.app['containers'][0]['endpoints'][0]['labels'] = \
                {'VIP_0': vip}
        if network == marathon.Network.USER:
            del self.app['containers'][0]['endpoints'][0]['hostPort']
            self.app['containers'][0]['endpoints'][0][
                'containerPort'] = container_port
            self.app['networks'] = [{
                'name': network_name,
                'mode': 'container',
            }]
        elif network == marathon.Network.BRIDGE:
            self.app['containers'][0]['endpoints'][0][
                'containerPort'] = container_port
            self.app['networks'] = [{'mode': 'container/bridge'}]

    def __str__(self):
        return str(self.app)

    def deploy(self, dcos_api_session):
        return dcos_api_session.marathon.post(
            '/v2/pods', json=self.app).raise_for_status()

    @retrying.retry(
        wait_fixed=5000,
        stop_max_delay=20 * 60 * 1000,
        retry_on_result=lambda res: res is False)
    def wait(self, dcos_api_session):
        r = dcos_api_session.marathon.get('/v2/pods/{}::status'.format(
            self.id))
        assert_response_ok(r)

        self._info = r.json()
        error_msg = 'Status was {}: {}'.format(
            self._info['status'], self._info.get('message', 'no message'))
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
            port = info['instances'][0]['containers'][0]['endpoints'][0][
                'allocatedHostPort']
        return host, port

    def purge(self, dcos_api_session):
        return dcos_api_session.marathon.delete('/v2/pods/{}'.format(self.id))


def unused_port():
    global GLOBAL_PORT_POOL
    return next(GLOBAL_PORT_POOL)


def unused_octet():
    global GLOBAL_OCTET_POOL
    return next(GLOBAL_OCTET_POOL)


def lb_enabled():
    expanded_config = test_helpers.get_expanded_config()
    return expanded_config['enable_lb'] == 'true'


@retrying.retry(
    wait_fixed=2000,
    stop_max_delay=5 * 60 * 1000,
    retry_on_result=lambda ret: ret is None)
def ensure_routable(cmd, host, port, json_output=True):
    proxy_uri = 'http://{}:{}/run_cmd'.format(host, port)
    log.info('Sending {} data: {}'.format(proxy_uri, cmd))
    response = requests.post(proxy_uri, data=cmd, timeout=5).json()
    log.info('Requests Response: {}'.format(repr(response)))
    if response['status'] != 0:
        return None
    return json.loads(
        response['output']) if json_output else response['output']


def generate_vip_app_permutations():
    """ Generate all possible network interface permutations for applying vips
    """
    containers = list(marathon.Container) + [Container.POD]
    return [(container, vip_net, proxy_net) for container in containers
            for vip_net in list(marathon.Network)
            for proxy_net in list(marathon.Network)]


def workload_test(dcos_api_session, container, app_net, proxy_net, ipv6,
                  proxy_and_origin_same_host):
    (vip, hosts, cmd, origin_app, proxy_app, _pm_app) = \
        vip_workload_test(dcos_api_session, container,
                          app_net, proxy_net, ipv6, True,
                          proxy_and_origin_same_host, False)
    return (hosts, origin_app, proxy_app)


@pytest.mark.first
def test_docker_image_availablity():
    assert test_helpers.docker_pull_image(
        "debian:stretch-slim"), "docker pull failed for image used in the test"


@pytest.mark.slow
@pytest.mark.parametrize('proxy_and_origin_same_host', [True, False])
def test_ipv6(dcos_api_session, proxy_and_origin_same_host):
    ''' Testing autoip, containerip and *.mesos FQDN on ipv6 overlay network'''
    (hosts, origin_app, proxy_app) = \
        workload_test(dcos_api_session, marathon.Container.DOCKER,
                      marathon.Network.USER, marathon.Network.USER,
                      True, proxy_and_origin_same_host)
    log.info('Starting apps :: Hosts: {}'.format(hosts))
    log.info("Origin app: {}".format(origin_app))
    origin_app.deploy(dcos_api_session)
    log.info("Proxy app: {}".format(proxy_app))
    proxy_app.deploy(dcos_api_session)
    origin_app.wait(dcos_api_session)
    proxy_app.wait(dcos_api_session)
    log.info('Apps are ready')
    origin_app_info = origin_app.info(dcos_api_session)
    origin_port = origin_app_info['app']['container']['portMappings'][0][
        'containerPort']
    proxy_host, proxy_port = proxy_app.hostport(dcos_api_session)
    dns_name = '-'.join(reversed(origin_app.id.split('/')[1:]))
    try:
        zones = [
            "marathon.autoip.dcos.thisdcos.directory",
            "marathon.containerip.dcos.thisdcos.directory",
            "marathon.mesos",
        ]
        for zone in zones:
            cmd = '{} --ipv6 http://{}/test_uuid'.format(
                '/opt/mesosphere/bin/curl -s -f -m 5', '{}.{}:{}'.format(
                    dns_name, zone, origin_port))
            log.info("Remote command: {}".format(cmd))
            assert ensure_routable(cmd, proxy_host,
                                   proxy_port)['test_uuid'] == origin_app.uuid
    finally:
        log.info('Purging application: {}'.format(origin_app.id))
        origin_app.purge(dcos_api_session)
        log.info('Purging application: {}'.format(proxy_app.id))
        proxy_app.purge(dcos_api_session)


@pytest.mark.slow
@pytest.mark.parametrize('is_named_vip', [True, False])
@pytest.mark.parametrize('proxy_and_origin_same_host', [True, False])
def test_vip_ipv6(dcos_api_session, is_named_vip, proxy_and_origin_same_host):
    vip_test_base(
        dcos_api_session,
        container_type=marathon.Container.DOCKER,
        origin_network_type=marathon.Network.USER,
        proxy_network_type=marathon.Network.USER,
        is_named_vip=is_named_vip,
        proxy_and_origin_same_host=proxy_and_origin_same_host,
        ipv6=True,
        origin_network_name="dcos6",
        proxy_network_name="dcos6")


@pytest.mark.slow
@pytest.mark.parametrize('container_type', list(marathon.Container))
@pytest.mark.parametrize('proxy_and_origin_same_host', [True, False])
def test_vip_port_mapping(dcos_api_session, container_type: marathon.Container,
                          proxy_and_origin_same_host: bool):
    # requests to vip address were hijacked by a container with host port the
    # same as VIP port, tracked in DCOS_OSS-5061. This test is to validate this
    # problem is resloved.
    vip_test_base(
        dcos_api_session,
        container_type,
        origin_network_type=marathon.Network.HOST,
        proxy_network_type=marathon.Network.HOST,
        is_named_vip=False,
        proxy_and_origin_same_host=proxy_and_origin_same_host,
        with_port_mapping_app=True)


@pytest.mark.parametrize('container_type',
                         list(marathon.Container) + [Container.POD])
@pytest.mark.parametrize('origin_network_type', list(marathon.Network))
@pytest.mark.parametrize('proxy_network_type', list(marathon.Network))
@pytest.mark.parametrize('is_named_vip', [True, False])
@pytest.mark.parametrize('proxy_and_origin_same_host', [True, False])
def test_vip(dcos_api_session, container_type, origin_network_type,
             proxy_network_type, is_named_vip, proxy_and_origin_same_host):
    vip_test_base(dcos_api_session, container_type, origin_network_type,
                  proxy_network_type, is_named_vip, proxy_and_origin_same_host)


def vip_test_base(dcos_api_session,
                  container_type,
                  origin_network_type,
                  proxy_network_type,
                  is_named_vip,
                  proxy_and_origin_same_host,
                  ipv6=False,
                  with_port_mapping_app=False,
                  origin_network_name="dcos",
                  proxy_network_name="dcos"):
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

    if len(dcos_api_session.all_slaves) <= 1 and proxy_and_origin_same_host:
        pytest.skip(
            'Not enough slaves for deploying proxy and origin container'
            ' on different host')

    test_suit = vip_workload_test(
        dcos_api_session, container_type, origin_network_type,
        proxy_network_type, ipv6, is_named_vip, proxy_and_origin_same_host,
        origin_network_name, proxy_network_name)

    vip_addr = test_suit.vip_addr()
    vip_port = vip_addr.split(':')[-1]
    proxy_app = test_suit.proxy_app()
    origin_app = test_suit.origin_app()
    apps = [proxy_app, origin_app]
    app_hosts = test_suit.app_hosts()
    cmd = test_suit.proxy_cmd()

    log.info('Starting apps :: VIP: {}, Hosts: {}'.format(vip_addr, app_hosts))
    log.info("Origin app: {}".format(origin_app))
    log.info("Proxy app: {}".format(proxy_app))
    log.info("Testing :: VIP: {}, Hosts: {}".format(vip_addr, app_hosts))
    log.info("Remote command: {}".format(cmd))

    if with_port_mapping_app:
        # Port mapping application runs on `proxy_host` and has the `host_port`
        # same as `vip_port`.
        pm_fmt = test_suit.app_name_format("pm")
        pm_container = Container.MESOS if container_type == Container.POD \
            else container_type
        pm_app = MarathonApp(
            pm_container,
            marathon.Network.BRIDGE,
            test_suit.proxy_host,
            host_port=int(vip_port),
            app_name_fmt=pm_fmt)
        apps.append(pm_app)

    for app in apps:
        log.info("deploying app: {}".format(app))
        app.deploy(dcos_api_session)
    for app in apps:
        log.info("waiting app to be ready: {}".format(app.id))
        app.wait(dcos_api_session)
    log.info("apps are ready")

    proxy_ip_address, proxy_port = proxy_app.hostport(dcos_api_session)

    try:
        if ipv6 and len(app_hosts) < 2:
            # NOTE: If proxy and origin apps run on the same host, IPv6 VIP
            # works from proxy task's network namespace only when
            # bridge-nf-call-ip6tables is enabled, i.e
            # sysctl -w net.bridge.bridge-nf-call-ip6tables=1
            # JIRA: https://jira.mesosphere.com/browse/DCOS_OSS-5122
            return
        assert ensure_routable(cmd, proxy_ip_address,
                               proxy_port)['test_uuid'] == origin_app.uuid
    except Exception as e:
        pytest.fail('Exception: {}'.format(e))
    finally:
        for app in apps:
            log.info("destroy app: {}".format(app.id))
            app.wait(dcos_api_session)


class VipTestSuit():
    """ manages variables for a vip test depending on different cases """

    def __init__(self, dcos_api_session, container_type, origin_network_type,
                 proxy_network_type):
        self._vip_port = unused_port()
        self._container_type = container_type
        self._origin_network_type = origin_network_type
        self._proxy_network_type = proxy_network_type
        self._slaves = dcos_api_session.slaves + dcos_api_session.public_slaves
        self.origin_host = self._slaves[0]
        self.proxy_host = self._slaves[0]
        self._proxy_app = None
        self._origin_app = None
        self._is_ipv6 = False
        self._is_named_vip = False
        self._named_vip_addr_ipv4 = None
        self._vip_addr_ipv6 = None
        self._vip_addr_ipv4 = self._vip_addr_ipv4 = self._vip_addr = None
        self._proxy_and_origin_same_host = False
        self._proxy_network_name = "dcos"
        self._origin_network_name = "dcos"

    def is_ipv6(self):
        """ eanble ipv6 """
        self._is_ipv6 = True

    def set_origin_network_name(self, network_name):
        """ sets the network name of the origin application

        When the container network is set `USER`, this function should be
        called when the network name is not the default one, `dcos`.
        """
        self._origin_network_name = network_name

    def set_proxy_network_name(self, network_name):
        """ sets the network name of proxy application

        When the container network is set `USER`, this function should be
        called when the network name is not the default one, `dcos`.
        """
        self._proxy_network_name = network_name

    def is_named_vip(self):
        self._is_named_vip = True

    def proxy_and_origin_not_same_host(self):
        if len(self._slaves) > 1:
            self.proxy_host = self._slaves[1]
        else:
            err_msg = 'the number of slave {} is less than 2'.format(
                self._slave)
            raise Exception(err_msg)

    def vip_addr(self):
        """ provides the vip address of the test app """
        if self._is_named_vip:
            return self._get_named_vip_addr()
        if self._is_ipv6:
            return self._get_vip_addr_ipv6()

        return self._get_vip_addr_ipv4()

    def app_hosts(self):
        return list(set([self.proxy_host, self.origin_host]))

    def _get_named_vip_addr(self):
        if self._named_vip_addr_ipv4 is not None:
            return self._named_vip_addr_ipv4
        label = str(uuid.uuid4())
        self._vip = '/{}:{}'.format(label, self._vip_port)
        vip_addr = '{}.marathon.l4lb.thisdcos.directory:{}'.format(
            label, self._vip_port)
        self._named_vip_addr_ipv4 = vip_addr
        return self._named_vip_addr_ipv4

    def _get_vip_addr_ipv4(self):
        if self._vip_addr_ipv4 is not None:
            return self._vip_addr_ipv4
        vip = '198.51.100.{}:{}'.format(unused_octet(), self._vip_port)
        self._vip = vip
        self._vip_addr_ipv4 = vip
        return self._vip_addr_ipv4

    def _get_vip_addr_ipv6(self):
        if self._vip_addr_ipv6 is not None:
            return self._vip_addr_ipv6
        vip_ip = 'fd01:c::{}'.format(unused_octet())
        self._vip = '{}:{}'.format(vip_ip, self._vip_port)
        vip_addr_ipv6 = '[{}]:{}'.format(vip_ip, self._vip_port)
        self._vip_addr_ipv6 = vip_addr_ipv6
        return self._vip_addr_ipv6

    def app_name_format(self, app_type):
        """ provides an unique app path among test cases

        Args:
            app_type: the functionality of the app. It can be `proxy` for
                      proxy container, and `app` for the original container
        """

        path_id = '/integration-tests/{}-{}-{}'.format(
            enum2str(self._container_type),
            net2str(self._origin_network_type, self._is_ipv6),
            net2str(self._proxy_network_type, self._is_ipv6))
        uid = self.uuid = uuid.uuid4().hex[:5]
        same_host = True if self.proxy_host == self.origin_host else False
        test_case_id = '{}-{}'.format('named' if self._is_named_vip else 'vip',
                                      'local' if same_host else 'remote')
        name_format = '{}/{}-{}-{}'.format(path_id, app_type, test_case_id,
                                           uid)
        return name_format

    def proxy_cmd(self):
        cmd = '{} {} http://{}/test_uuid'.format(
            '/opt/mesosphere/bin/curl -s -f -m 5',
            '--ipv6' if self._is_ipv6 else '--ipv4', self.vip_addr())
        return cmd

    def proxy_app(self):
        if self._proxy_app is not None:
            return self._proxy_app
        proxy_name_format = self.app_name_format("proxy")
        if self._container_type == Container.POD:
            proxy_app = MarathonPod(
                self._proxy_network_type,
                self.proxy_host,
                pod_name_fmt=proxy_name_format)
        else:
            proxy_app = MarathonApp(
                self._container_type,
                self._proxy_network_type,
                self.proxy_host,
                network_name=self._proxy_network_name,
                app_name_fmt=proxy_name_format)
        self._proxy_app = proxy_app
        return self._proxy_app

    def origin_app(self):
        if self._origin_app is not None:
            return self._origin_app
        # call vip_addr to intialize self._vip
        self.vip_addr()
        origin_fmt = self.app_name_format("app")
        if self._container_type == Container.POD:
            origin_app = MarathonPod(
                self._origin_network_type,
                self.origin_host,
                self._vip,
                pod_name_fmt=origin_fmt)
        else:
            origin_app = MarathonApp(
                self._container_type,
                self._origin_network_type,
                self.origin_host,
                self._vip,
                network_name=self._origin_network_name,
                app_name_fmt=origin_fmt)
        self._origin_app = origin_app
        return self._origin_app


def vip_workload_test(dcos_api_session,
                      container_type,
                      origin_network_type,
                      proxy_network_type,
                      ipv6=False,
                      is_named_vip=False,
                      proxy_and_origin_same_host=False,
                      origin_network_name='dcos',
                      proxy_network_name='dcos'):

    test_suit = VipTestSuit(dcos_api_session, container_type,
                            origin_network_type, proxy_network_type)

    if ipv6:
        test_suit.is_ipv6()
    if is_named_vip:
        test_suit.is_named_vip()
    if not proxy_and_origin_same_host:
        test_suit.proxy_and_origin_not_same_host()
    if origin_network_type == marathon.Network.USER:
        test_suit.set_origin_network_name(origin_network_name)
    if proxy_network_type == marathon.Network.USER:
        test_suit.set_proxy_network_name(proxy_network_name)

    return test_suit


@retrying.retry(wait_fixed=2000,
                stop_max_delay=120 * 1000,
                retry_on_exception=lambda x: True)
def test_if_overlay_ok(dcos_api_session):
    def _check_overlay(hostname, port):
        overlays = dcos_api_session.get(
            '/overlay-agent/overlay', host=hostname,
            port=port).json()['overlays']
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
    '''Test if we are able to connect to a task with ip-per-container mode'''
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

    with dcos_api_session.marathon.deploy_and_cleanup(
            app_definition, check_health=True):
        service_points = dcos_api_session.marathon.get_app_service_endpoints(
            app_definition['id'])
        app_port = app_definition['container']['portMappings'][0][
            'containerPort']
        cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}:{}/ping'.format(
            service_points[1].ip, app_port)
        ensure_routable(cmd, service_points[0].host, service_points[0].port)


@pytest.mark.parametrize('networking_mode', list(marathon.Network))
@pytest.mark.parametrize('host_port', [9999, 0])
def test_app_networking_mode_with_defined_container_port(
        dcos_api_session, networking_mode, host_port):
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
    #  https://github.com/dcos/dcos/blob/cb9105ee537cc44cbe63cc7c53b3b01b764703a0/packages/adminrouter/extra/src/includes/http/master.conf#L21 # NOQA
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
    with dcos_api_session.marathon.deploy_and_cleanup(
            app_definition, check_health=False):
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


def test_l4lb(dcos_api_session):
    '''Test l4lb is load balancing between all the backends
       * create 5 apps using the same VIP
       * get uuid from the VIP
       * verify that 5 uuids have been returned
       * only testing if all 5 are hit at least once
    '''

    @retrying.retry(
        wait_fixed=2000,
        stop_max_delay=100 * 2000,
        retry_on_exception=lambda x: True)
    def getjson(url):
        r = requests.get(url)
        r.raise_for_status()
        return r.json()

    numapps = 5
    apps = []
    try:
        for i in range(numapps):
            app = MarathonApp(
                marathon.Container.MESOS,
                marathon.Network.HOST,
                vip='/l4lbtest:5000',
                app_name_fmt='/integration-test/l4lb/app-{}')
            app.app['portDefinitions'][0]['labels'][
                'VIP_1'] = '/app-{}:80'.format(i)
            log.info('App: {}'.format(app))
            app.deploy(dcos_api_session)
            apps.append(app)
        for app in apps:
            log.info('Deploying app: {}'.format(app.id))
            app.wait(dcos_api_session)
        log.info('Apps are ready')

        for i in range(numapps):
            getjson('http://app-{}.marathon.l4lb.thisdcos.directory/ping'.
                    format(i))
        log.info('L4LB is ready')

        vip = 'l4lbtest.marathon.l4lb.thisdcos.directory:5000'
        vips = getjson("http://localhost:62080/v1/vips")
        log.info('VIPs: {}'.format(vips))

        backends = [app.hostport(dcos_api_session) for app in apps]
        for backend in [
                b for v in vips if v['vip'] == vip for b in v['backend']
        ]:
            backends.remove((backend['ip'], backend['port']))
        assert backends == []

        vipurl = 'http://{}/test_uuid'.format(vip)
        uuids = set(
            [(getjson(vipurl))['test_uuid'] for _ in range(numapps * numapps)])
        assert uuids == set([app.uuid for app in apps])
    finally:
        for app in apps:
            log.info('Purging app: {}'.format(app.id))
            app.purge(dcos_api_session)


def test_dcos_cni_l4lb(dcos_api_session):
    '''
    This tests the `dcos - l4lb` CNI plugins:
        https: // github.com / dcos / dcos - cni / tree / master / cmd / l4lb

    The `dcos-l4lb` CNI plugins allows containers running on networks that
    don't necessarily have routes to spartan interfaces and minuteman VIPs to
    consume DNS service from spartan and layer-4 load-balancing services from
    minuteman by injecting spartan and minuteman services into the container's
    network namespace. You can read more about the motivation for this CNI
    plugin and type of problems it solves in this design doc:

    https://docs.google.com/document/d/1xxvkFknC56hF-EcDmZ9tzKsGiZdGKBUPfrPKYs85j1k/edit?usp=sharing # NOQA

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
    contianer's netns, we start a client on the `spartan-net` and try to `curl`
    the `ping-pong` server using its VIP. Without the Minuteman and Spartan
    services injected in the container's netns the expectation would be that
    this `curl` would fail, with a successful `curl` execution on the VIP
    allowing the test-case to PASS.
    '''
    if not lb_enabled():
        pytest.skip('Load Balancer disabled')

    expanded_config = test_helpers.get_expanded_config()
    if expanded_config.get('security') == 'strict':
        pytest.skip('Cannot setup CNI config with EE strict mode enabled')

    # Run all the test application on the first agent node
    host = dcos_api_session.slaves[0]

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
                    'type':
                    'host-local',
                    'subnet':
                    '192.168.250.0/24',
                    'routes': [
                        # Reachability to DC/OS overlay.
                        {
                            'dst': '9.0.0.0/8',
                        },
                        # Reachability to all private address subnet. We need
                        # this reachability since different cloud providers use
                        # different private address spaces to launch tenant
                        # networks.
                        {
                            'dst': '10.0.0.0/8',
                        },
                        {
                            'dst': '172.16.0.0/12',
                        },
                        {
                            'dst': '192.168.0.0/16',
                        },
                    ],
                },
            },
        },
    }

    log.info("spartan-net config:{}".format(json.dumps(spartan_net)))

    # Application to deploy CNI configuration.
    cni_config_app = MarathonApp(
        marathon.Container.NONE,
        marathon.Network.HOST,
        host,
        app_name_fmt='/integration-test/cni-l4lb/config-{}')

    # Override the default test app command with a command to write the CNI
    # configuration.
    #
    # NOTE: We add the original command at the end of this command so that the
    # task stays alive for the test harness to make sure that the task got
    # deployed. Ideally we should be able to deploy one of tasks using the test
    # harness but that doesn't seem to be the case here.
    cni_config_app.app['cmd'] = \
        "echo '{}' > {} && {}".format(
            json.dumps(spartan_net),
            '/opt/mesosphere/etc/dcos/network/cni/spartan.cni',
            cni_config_app.app['cmd'])

    log.info("CNI Config application: {}".format(cni_config_app.app))
    try:
        cni_config_app.deploy(dcos_api_session)
        cni_config_app.wait(dcos_api_session)
    finally:
        cni_config_app.purge(dcos_api_session)
    log.info("CNI Config has been deployed on {}".format(host))

    # Get the host on which the `spartan-net` was installed.
    # Launch the test-app on DC/OS overlay, with a VIP.
    server_vip_label = '/spartanvip:10000'
    server_vip_addr = 'spartanvip.marathon.l4lb.thisdcos.directory:10000'

    # Launch the test_server in ip-per-container mode (user network)
    server_app = MarathonApp(
        marathon.Container.MESOS,
        marathon.Network.USER,
        host,
        vip=server_vip_label,
        app_name_fmt='/integration-test/cni-l4lb/server-{}')
    log.info("Server application: {}".format(server_app.app))

    # Get the client app on the 'spartan-net' network.
    client_app = MarathonApp(
        marathon.Container.MESOS,
        marathon.Network.USER,
        host,
        network_name='spartan-net',
        app_name_fmt='/integration-test/cni-l4lb/client-{}')
    log.info("Client application: {}".format(client_app.app))

    try:
        # Launch the test application
        client_app.deploy(dcos_api_session)
        server_app.deploy(dcos_api_session)

        # Wait for the test application
        server_app.wait(dcos_api_session)
        client_app.wait(dcos_api_session)

        client_host, client_port = client_app.hostport(dcos_api_session)

        # Check linux kernel version
        uname = ensure_routable(
            'uname -r', client_host, client_port, json_output=False)
        if '3.10.0-862' <= uname < '3.10.0-898':
            return pytest.skip(
                'See https://bugzilla.redhat.com/show_bug.cgi?id=1572983')

        # Change the client command task to do a curl on the server we just
        # deployed.
        cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}/test_uuid'.format(
            server_vip_addr)

        assert ensure_routable(cmd, client_host,
                               client_port)['test_uuid'] == server_app.uuid
    finally:
        server_app.purge(dcos_api_session)
        client_app.purge(dcos_api_session)


def enum2str(value):
    return str(value).split('.')[-1].lower()


def net2str(value, ipv6):
    return enum2str(value) if not ipv6 else 'ipv6'


@retrying.retry(
    wait_fixed=2000,
    stop_max_delay=100 * 2000,
    retry_on_exception=lambda x: True)
def test_dcos_net_cluster_identity(dcos_api_session):
    cluster_id = 'minuteman'  # default

    expanded_config = test_helpers.get_expanded_config()
    if expanded_config['dcos_net_cluster_identity'] == 'true':
        with open('/var/lib/dcos/cluster-id') as f:
            cluster_id = "'{}'".format(f.readline().rstrip())

    argv = [
        'sudo',
        '/opt/mesosphere/bin/dcos-net-env',
        'eval',
        'erlang:get_cookie().',
    ]
    cookie = subprocess.check_output(
        argv, stderr=subprocess.STDOUT).decode('utf-8').rstrip()

    assert cluster_id == cookie, "cluster_id: {}, cookie: {}".format(
        cluster_id, cookie)
