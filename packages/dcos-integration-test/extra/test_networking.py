import enum
import itertools
import json
import logging
import subprocess
import time
import uuid
from ipaddress import IPv4Address, IPv4Network

from typing import Any, Optional

import pytest
import requests
import retrying
import test_helpers

from dcos_test_utils import marathon
from dcos_test_utils.dcos_api import DcosApiSession
from dcos_test_utils.helpers import assert_response_ok

__maintainer__ = 'urbanserj'
__contact__ = 'dcos-networking@mesosphere.io'

log = logging.getLogger(__name__)

GLOBAL_PORT_POOL = iter(range(10000, 32000))
GLOBAL_OCTET_POOL = itertools.cycle(range(254, 10, -1))

# Apply fixture(s) in this list to all tests in this module. From
# pytest docs: "Note that the assigned variable must be called pytestmark"
pytestmark = [pytest.mark.usefixtures("clean_marathon_state_function_scoped")]


class Container(enum.Enum):
    POD = 'POD'


class InternalUserNetwork(enum.Enum):
    """User networks supported internally in DC/OS by default"""
    DCOS = 'dcos'
    CALICO = 'calico'

    @staticmethod
    def has_value(item: str) -> bool:
        return item in [v.value for v in InternalUserNetwork.__members__.values()]


class MarathonApp:
    def __init__(self, container: marathon.Container, network: marathon.Network,
                 host: Optional[str] = None, vip: Optional[str] = None, network_name: Optional[str] = None,
                 app_name_fmt: Optional[str] = None, host_port: Optional[int] = None):
        if host_port is None:
            host_port = unused_port()
        args = {
            'app_name_fmt': app_name_fmt,
            'network': network,
            'host_port': host_port,
            'vip': vip,
            'container_type': container,
            'healthcheck_protocol': marathon.Healthcheck.MESOS_HTTP
        }
        if host is not None:
            args['host_constraint'] = host
        if network == marathon.Network.USER:
            args['container_port'] = unused_port()
            if network_name is not None:
                args['network_name'] = network_name
            if vip is not None:
                del args['host_port']
        self.app, self.uuid = test_helpers.marathon_test_app(**args)  # type: ignore
        # allow this app to run on public slaves
        self.app['acceptedResourceRoles'] = ['*']
        self.id = self.app['id']

    def __str__(self) -> str:
        return str(self.app)

    def deploy(self, dcos_api_session: DcosApiSession) -> Any:
        return dcos_api_session.marathon.post('/v2/apps', json=self.app).raise_for_status()

    @retrying.retry(
        wait_fixed=5000,
        stop_max_delay=20 * 60 * 1000)
    def wait(self, dcos_api_session: DcosApiSession) -> None:
        r = dcos_api_session.marathon.get('/v2/apps/{}'.format(self.id))
        assert_response_ok(r)

        self._info = r.json()
        assert self._info['app']['tasksHealthy'] == self.app['instances']

    def info(self, dcos_api_session: DcosApiSession) -> Any:
        try:
            if self._info['app']['tasksHealthy'] != self.app['instances']:
                raise Exception("Number of Healthy Tasks not equal to number of instances.")
        except Exception:
            self.wait(dcos_api_session)
        return self._info

    def hostport(self, dcos_api_session: DcosApiSession) -> tuple:
        """ returns container ip and port for calico and dcos network otherwise the ones from the host
        """
        info = self.info(dcos_api_session)
        task = info['app']['tasks'][0]
        if 'networks' in self.app and \
                self.app['networks'][0]['mode'] == 'container' and \
                InternalUserNetwork.has_value(self.app['networks'][0]['name']):
            host = task['ipAddresses'][0]['ipAddress']
            port = self.app['container']['portMappings'][0]['containerPort']
        else:
            host = task['host']
            port = task['ports'][0]
        return host, port

    def purge(self, dcos_api_session: DcosApiSession) -> Any:
        return dcos_api_session.marathon.delete('/v2/apps/{}'.format(self.id))


class MarathonPod:
    def __init__(self, network: str, host: str, vip: Any = None, pod_name_fmt: str = '/integration-test-{}',
                 network_name: str = "dcos"):
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
            'scheduling': {'placement': {'acceptedResourceRoles': ['*']}},
            'containers': [{
                'name': 'app-{}'.format(self.uuid),
                'resources': {'cpus': 0.01, 'mem': 32},
                'image': {'kind': 'DOCKER', 'id': 'debian:stretch-slim'},
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
            self.app['scheduling']['placement']['constraints'] = [{  # type: ignore
                'fieldName': 'hostname', 'operator': 'CLUSTER', 'value': host
            }]
        if vip is not None:
            self.app['containers'][0]['endpoints'][0]['labels'] = {'VIP_0': vip}  # type: ignore
        if network == marathon.Network.USER:
            del self.app['containers'][0]['endpoints'][0]['hostPort']  # type: ignore
            self.app['containers'][0]['endpoints'][0]['containerPort'] = container_port  # type: ignore
            self.app['networks'] = [{'name': network_name, 'mode': 'container'}]
        elif network == marathon.Network.BRIDGE:
            self.app['containers'][0]['endpoints'][0]['containerPort'] = container_port  # type: ignore
            self.app['networks'] = [{'mode': 'container/bridge'}]

    def __str__(self) -> str:
        return str(self.app)

    def deploy(self, dcos_api_session: DcosApiSession) -> Any:
        return dcos_api_session.marathon.post('/v2/pods', json=self.app).raise_for_status()

    @retrying.retry(
        wait_fixed=5000,
        stop_max_delay=20 * 60 * 1000,
        retry_on_result=lambda res: res is False)
    def wait(self, dcos_api_session: DcosApiSession) -> None:
        r = dcos_api_session.marathon.get('/v2/pods/{}::status'.format(self.id))
        assert_response_ok(r)

        self._info = r.json()
        error_msg = 'Status was {}: {}'.format(self._info['status'], self._info.get('message', 'no message'))
        assert self._info['status'] == 'STABLE', error_msg

    def info(self, dcos_api_session: DcosApiSession) -> Any:
        try:
            if self._info['status'] != 'STABLE':
                raise Exception("The status information is not Stable!")
        except Exception:
            self.wait(dcos_api_session)
        return self._info

    def hostport(self, dcos_api_session: DcosApiSession) -> tuple:
        info = self.info(dcos_api_session)
        if self._network == marathon.Network.USER:
            host = info['instances'][0]['networks'][0]['addresses'][0]
            port = self.app['containers'][0]['endpoints'][0]['containerPort']  # type: ignore
        else:
            host = info['instances'][0]['agentHostname']
            port = info['instances'][0]['containers'][0]['endpoints'][0]['allocatedHostPort']
        return host, port

    def purge(self, dcos_api_session: DcosApiSession) -> Any:
        return dcos_api_session.marathon.delete('/v2/pods/{}'.format(self.id))


def unused_port() -> int:
    global GLOBAL_PORT_POOL
    return next(GLOBAL_PORT_POOL)


def unused_octet() -> int:
    global GLOBAL_OCTET_POOL
    return next(GLOBAL_OCTET_POOL)


def lb_enabled() -> Any:
    expanded_config = test_helpers.get_expanded_config()
    return expanded_config['enable_lb'] == 'true'


@retrying.retry(wait_fixed=2000,
                stop_max_delay=5 * 60 * 1000,
                retry_on_result=lambda ret: ret is None,
                retry_on_exception=lambda e: isinstance(e, Exception))
def ensure_routable(cmd: str, host: str, port: str, json_output: bool = True) -> Any:
    proxy_uri = 'http://{}:{}/run_cmd'.format(host, port)
    log.info('Sending {} data: {}'.format(proxy_uri, cmd))
    response = requests.post(proxy_uri, data=cmd, timeout=5).json()
    log.info('Requests Response: {}'.format(repr(response)))
    if response['status'] != 0:
        return None
    return json.loads(response['output']) if json_output else response['output']


def generate_vip_app_permutations() -> list:
    """ Generate all possible network interface permutations for applying vips
    """
    containers = list(marathon.Container) + [Container.POD]
    return [(container, vip_net, proxy_net)
            for container in containers
            for vip_net in list(marathon.Network)
            for proxy_net in list(marathon.Network)]


def workload_test(dcos_api_session: DcosApiSession, container: marathon.Container, app_net: Any, proxy_net: Any,
                  ipv6: bool, same_host: bool) -> tuple:
    (vip, hosts, cmd, origin_app, proxy_app, _pm_app) = \
        vip_workload_test(dcos_api_session, container,
                          app_net, proxy_net, ipv6, True, same_host, False)
    return (hosts, origin_app, proxy_app)


@pytest.mark.first
def test_docker_image_availablity() -> None:
    assert test_helpers.docker_pull_image("debian:stretch-slim"), "docker pull failed for image used in the test"


@pytest.mark.slow
@pytest.mark.parametrize('same_host', [True, False])
def test_ipv6(dcos_api_session: DcosApiSession, same_host: bool) -> None:
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
            assert ensure_routable(cmd, proxy_host, proxy_port)['test_uuid'] == origin_app.uuid
    finally:
        log.info('Purging application: {}'.format(origin_app.id))
        origin_app.purge(dcos_api_session)
        log.info('Purging application: {}'.format(proxy_app.id))
        proxy_app.purge(dcos_api_session)


@pytest.mark.slow
def test_vip_ipv6(dcos_api_session: DcosApiSession) -> Any:
    return test_vip(dcos_api_session, marathon.Container.DOCKER,
                    marathon.Network.USER, marathon.Network.USER, ipv6=True)


@pytest.mark.slow
@pytest.mark.parametrize(
    'container',
    list(marathon.Container))
def test_vip_port_mapping(dcos_api_session: DcosApiSession,
                          container: marathon.Container,
                          vip_net: marathon.Network=marathon.Network.HOST,
                          proxy_net: marathon.Network=marathon.Network.HOST) -> Any:
    return test_vip(dcos_api_session, container, vip_net, proxy_net, with_port_mapping_app=True)


@pytest.mark.slow
@pytest.mark.parametrize(
    'container,vip_net,proxy_net',
    generate_vip_app_permutations())
def test_vip(dcos_api_session: DcosApiSession,
             container: marathon.Container,
             vip_net: marathon.Network,
             proxy_net: marathon.Network,
             ipv6: bool = False,
             with_port_mapping_app: bool = False) -> list:
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
    tests = setup_vip_workload_tests(dcos_api_session, container, vip_net, proxy_net, ipv6, with_port_mapping_app)
    for vip, hosts, cmd, origin_app, proxy_app, pm_app in tests:
        log.info("Testing :: VIP: {}, Hosts: {}".format(vip, hosts))
        log.info("Remote command: {}".format(cmd))
        proxy_host, proxy_port = proxy_app.hostport(dcos_api_session)
        try:
            if ipv6 and len(hosts) < 2:
                # NOTE: If proxy and origin apps run on the same host, IPv6 VIP works from
                # proxy task's network namespace only when bridge-nf-call-ip6tables is enabled, i.e
                # sysctl -w net.bridge.bridge-nf-call-ip6tables=1
                # JIRA: https://jira.mesosphere.com/browse/DCOS_OSS-5122
                continue
            assert ensure_routable(cmd, proxy_host, proxy_port)['test_uuid'] == origin_app.uuid
        except Exception as e:
            log.error('Exception: {}'.format(e))
            errors.append(e)
        finally:
            log.info('Purging application: {}'.format(origin_app.id))
            origin_app.purge(dcos_api_session)
            log.info('Purging application: {}'.format(proxy_app.id))
            proxy_app.purge(dcos_api_session)
            if pm_app is not None:
                log.info('Purging application: {}'.format(pm_app.id))
                pm_app.purge(dcos_api_session)
    assert not errors

    containers = list(marathon.Container) + [Container.POD]
    return [(container, vip_net, proxy_net)
            for container in containers
            for vip_net in list(marathon.Network)
            for proxy_net in list(marathon.Network)]


@pytest.mark.slow
@pytest.mark.parametrize('container', list(marathon.Container) + [Container.POD])
@pytest.mark.parametrize('vip_net', [marathon.Network.USER])
@pytest.mark.parametrize('proxy_net', [marathon.Network.USER])
def test_calico_vip(dcos_api_session: DcosApiSession,
                    container: marathon.Container,
                    vip_net: marathon.Network,
                    proxy_net: marathon.Network,
                    ipv6: bool = False,
                    with_port_mapping_app: bool =True) -> None:
    '''Test VIPs between the following source and destination configurations:
        * containers: UCR and POD
        * networks: USER
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
    tests = setup_vip_workload_tests(dcos_api_session, container, vip_net,
                                     proxy_net, ipv6, with_port_mapping_app,
                                     vip_network_name="calico",
                                     proxy_network_name="calico")
    for vip, hosts, cmd, origin_app, proxy_app, port_mapping_app in tests:
        log.info("Testing :: VIP: {}, Hosts: {}".format(vip, hosts))
        log.info("Remote command: {}".format(cmd))
        proxy_host, proxy_port = proxy_app.hostport(dcos_api_session)
        try:
            if ipv6 and len(hosts) < 2:
                # NOTE: If proxy and origin apps run on the same host, IPv6 VIP works from
                # proxy task's network namespace only when bridge-nf-call-ip6tables is enabled, i.e
                # sysctl -w net.bridge.bridge-nf-call-ip6tables=1
                # JIRA: https://jira.mesosphere.com/browse/DCOS_OSS-5122
                continue
            assert ensure_routable(cmd, proxy_host, proxy_port)['test_uuid'] == origin_app.uuid
        except Exception as e:
            log.error('Exception: {}'.format(e))
            errors.append(e)
        finally:
            log.info('Purging application: {}'.format(origin_app.id))
            origin_app.purge(dcos_api_session)
            log.info('Purging application: {}'.format(proxy_app.id))
            proxy_app.purge(dcos_api_session)
            if port_mapping_app is not None:
                log.info('Purging application: {}'.format(port_mapping_app.id))
                port_mapping_app.purge(dcos_api_session)
    assert not errors


def generate_vip_app_cross_usernetwork_permutations() -> list:
    """Generate cross user network combinations for vip"""
    return [(container, vip_network_name, proxy_network_name)
            for container in list(marathon.Container) + [Container.POD]
            for vip_network_name in list(InternalUserNetwork)
            for proxy_network_name in list(InternalUserNetwork)
            if vip_network_name != proxy_network_name]


@pytest.mark.slow
@pytest.mark.parametrize(
    'container,vip_network_name,proxy_network_name',
    generate_vip_app_cross_usernetwork_permutations())
def test_vip_cross_usernetwork(dcos_api_session: DcosApiSession,
                               container: marathon.Container,
                               vip_network_name: InternalUserNetwork,
                               proxy_network_name: InternalUserNetwork,
                               ipv6: bool = False) -> None:
    '''Test the vip connectivity between different user networks

    Origin app will be deployed to the cluster with a VIP. Proxy app will be
    deployed either to the same host or elsewhere. Finally, a thread will be
    started on localhost (which should be a master) to submit a command to the
    proxy container that will ping the origin container VIP and then assert
    that the expected origin app UUID was returned
    '''
    if not lb_enabled():
        pytest.skip('Load Balancer disabled')

    errors = []
    tests = setup_vip_workload_tests(dcos_api_session, container,
                                     marathon.Network.USER,
                                     marathon.Network.USER, ipv6,
                                     vip_network_name=vip_network_name,
                                     proxy_network_name=proxy_network_name)
    for vip, hosts, cmd, origin_app, proxy_app, port_mapping_app in tests:
        log.info("Testing :: VIP: {}, Hosts: {}".format(vip, hosts))
        log.info("Remote command: {}".format(cmd))
        proxy_host, proxy_port = proxy_app.hostport(dcos_api_session)
        try:
            if ipv6 and len(hosts) < 2:
                # NOTE: If proxy and origin apps run on the same host, IPv6 VIP works from
                # proxy task's network namespace only when bridge-nf-call-ip6tables is enabled, i.e
                # sysctl -w net.bridge.bridge-nf-call-ip6tables=1
                # JIRA: https://jira.mesosphere.com/browse/DCOS_OSS-5122
                continue
            assert ensure_routable(cmd, proxy_host, proxy_port)['test_uuid'] == origin_app.uuid
        except Exception as e:
            log.error('Exception: {}'.format(e))
            errors.append(e)
        finally:
            log.info('Purging application: {}'.format(origin_app.id))
            origin_app.purge(dcos_api_session)
            log.info('Purging application: {}'.format(proxy_app.id))
            proxy_app.purge(dcos_api_session)
            if port_mapping_app is not None:
                log.info('Purging application: {}'.format(port_mapping_app.id))
                port_mapping_app.purge(dcos_api_session)
    assert not errors


def setup_vip_workload_tests(dcos_api_session: DcosApiSession, container: marathon.Container, vip_net: Any,
                             proxy_net: Any, ipv6: bool, with_port_mapping_app: bool = False,
                             vip_network_name: Any = InternalUserNetwork.DCOS,
                             proxy_network_name: Any = InternalUserNetwork.DCOS) -> list:
    same_hosts = [True, False] if len(dcos_api_session.all_slaves) > 1 else [True]
    tests = [vip_workload_test(dcos_api_session, container, vip_net, proxy_net,
                               ipv6, named_vip, same_host,
                               with_port_mapping_app, vip_network_name,
                               proxy_network_name)
             for named_vip in [True, False]
             for same_host in same_hosts]
    for vip, hosts, cmd, origin_app, proxy_app, pm_app in tests:
        # We do not need the service endpoints because we have deterministically assigned them
        log.info('Starting apps :: VIP: {}, Hosts: {}'.format(vip, hosts))
        log.info("Origin app: {}".format(origin_app))
        origin_app.deploy(dcos_api_session)
        log.info("Proxy app: {}".format(proxy_app))
        proxy_app.deploy(dcos_api_session)
        if pm_app is not None:
            log.info("Port Mapping app: {}".format(pm_app))
            pm_app.deploy(dcos_api_session)
    for vip, hosts, cmd, origin_app, proxy_app, pm_app in tests:
        log.info("Deploying apps :: VIP: {}, Hosts: {}".format(vip, hosts))
        log.info('Deploying origin app: {}'.format(origin_app.id))
        origin_app.wait(dcos_api_session)
        log.info('Deploying proxy app: {}'.format(proxy_app.id))
        proxy_app.wait(dcos_api_session)
        if pm_app is not None:
            log.info("Deploying port mapping app: {}".format(pm_app))
            pm_app.wait(dcos_api_session)
        log.info('Apps are ready')
    return tests


def vip_workload_test(dcos_api_session: DcosApiSession, container: marathon.Container, vip_net: Any, proxy_net: Any,
                      ipv6: bool, named_vip: bool, same_host: bool, with_port_mapping_app: bool,
                      vip_network_name: Any = InternalUserNetwork.DCOS,
                      proxy_network_name: Any = InternalUserNetwork.DCOS) -> tuple:
    slaves = dcos_api_session.slaves + dcos_api_session.public_slaves
    vip_port = unused_port()
    origin_host = slaves[0]
    proxy_host = slaves[0] if same_host else slaves[1]
    if named_vip:
        label = str(uuid.uuid4())
        vip = '/{}:{}'.format(label, vip_port)
        vipaddr = '{}.marathon.l4lb.thisdcos.directory:{}'.format(label, vip_port)
    elif ipv6:
        vip_ip = 'fd01:c::{}'.format(unused_octet())
        vip = '{}:{}'.format(vip_ip, vip_port)
        vipaddr = '[{}]:{}'.format(vip_ip, vip_port)
    else:
        vip = '198.51.100.{}:{}'.format(unused_octet(), vip_port)
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
    # NOTE: we should overwrite the network name for only dcos overlay support
    # ipv6 for now. And it's safe to assign network name in advance because
    # MarathonPod will determined whether or not this network name is used by
    # the network mode.
    # it is used for user network mode only and only for 'dcos' networks.
    # NOTE: 'calico' IPV6 is not yet supported
    vip_network_name = enum2str(vip_network_name)
    proxy_network_name = enum2str(proxy_network_name)
    if ipv6:
        vip_network_name = '{}6'.format(vip_network_name)
        proxy_network_name = '{}6'.format(proxy_network_name)

    if container == Container.POD:
        origin_app = MarathonPod(vip_net, origin_host, vip, pod_name_fmt=origin_fmt, network_name=vip_network_name)
        proxy_app = MarathonPod(proxy_net, proxy_host, pod_name_fmt=proxy_fmt, network_name=proxy_network_name)
    else:
        origin_app = MarathonApp(container, vip_net, origin_host, vip,  # type: ignore
                                 network_name=vip_network_name, app_name_fmt=origin_fmt)
        proxy_app = MarathonApp(container, proxy_net, proxy_host,  # type: ignore
                                network_name=proxy_network_name, app_name_fmt=proxy_fmt)
    # Port mappiong application runs on `proxy_host` and has the `host_port` same as `vip_port`.
    pm_fmt = '{}/pm-{}'.format(path_id, test_case_id)
    pm_fmt = pm_fmt + '-{{:.{}}}'.format(63 - len(pm_fmt))
    if with_port_mapping_app:
        pm_container = marathon.Container.MESOS if container == Container.POD else container
        pm_app = MarathonApp(pm_container, marathon.Network.BRIDGE, proxy_host, host_port=vip_port, app_name_fmt=pm_fmt)
    else:
        pm_app = None  # type: ignore
    hosts = list(set([origin_host, proxy_host]))
    return (vip, hosts, cmd, origin_app, proxy_app, pm_app)


@retrying.retry(wait_fixed=2000,
                stop_max_delay=120 * 1000,
                retry_on_exception=lambda x: True)
def test_if_overlay_ok(dcos_api_session: DcosApiSession) -> None:
    def _check_overlay(hostname: str, port: int) -> None:
        overlays = dcos_api_session.get('/overlay-agent/overlay', host=hostname, port=port).json()['overlays']
        assert len(overlays) > 0
        for overlay in overlays:
            assert overlay['state']['status'] == 'STATUS_OK'

    for master in dcos_api_session.masters:
        _check_overlay(master, 5050)
    for slave in dcos_api_session.all_slaves:
        _check_overlay(slave, 5051)


def test_if_dcos_l4lb_disabled(dcos_api_session: DcosApiSession) -> None:
    '''Test to make sure dcos_l4lb is disabled'''
    if lb_enabled():
        pytest.skip('Load Balancer enabled')
    data = subprocess.check_output(['/usr/bin/env', 'ip', 'rule'])
    # dcos-net creates this ip rule: `9999: from 9.0.0.0/8 lookup 42`
    # We check it doesn't exist
    assert str(data).find('9999') == -1


def test_ip_per_container(dcos_api_session: DcosApiSession) -> None:
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
def test_app_networking_mode_with_defined_container_port(dcos_api_session: DcosApiSession,
                                                         networking_mode: marathon.Network,
                                                         host_port: int) -> None:
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


def test_l4lb(dcos_api_session: DcosApiSession) -> None:
    '''Test l4lb is load balancing between all the backends
       * create 5 apps using the same VIP
       * get uuid from the VIP
       * verify that 5 uuids have been returned
       * only testing if all 5 are hit at least once
    '''
    @retrying.retry(wait_fixed=2000,
                    stop_max_delay=100 * 2000,
                    retry_on_exception=lambda x: True)
    def getjson(url: str) -> Any:
        r = requests.get(url)
        r.raise_for_status()
        return r.json()

    numapps = 5
    apps = []
    try:
        for i in range(numapps):
            app = MarathonApp(marathon.Container.MESOS, marathon.Network.HOST, vip='/l4lbtest:5000',
                              app_name_fmt='/integration-test/l4lb/app-{}')
            app.app['portDefinitions'][0]['labels']['VIP_1'] = '/app-{}:80'.format(i)
            log.info('App: {}'.format(app))
            app.deploy(dcos_api_session)
            apps.append(app)
        for app in apps:
            log.info('Deploying app: {}'.format(app.id))
            app.wait(dcos_api_session)
        log.info('Apps are ready')

        for i in range(numapps):
            getjson('http://app-{}.marathon.l4lb.thisdcos.directory/ping'.format(i))
        log.info('L4LB is ready')

        vip = 'l4lbtest.marathon.l4lb.thisdcos.directory:5000'
        vips = getjson("http://localhost:62080/v1/vips")
        log.info('VIPs: {}'.format(vips))

        backends = [app.hostport(dcos_api_session) for app in apps]
        for backend in [b for v in vips if v['vip'] == vip for b in v['backend']]:
            backends.remove((backend['ip'], backend['port']))
        assert backends == []

        vipurl = 'http://{}/test_uuid'.format(vip)
        uuids = set([(getjson(vipurl))['test_uuid'] for _ in range(numapps * numapps)])
        assert uuids == set([app.uuid for app in apps])
    finally:
        for app in apps:
            log.info('Purging app: {}'.format(app.id))
            app.purge(dcos_api_session)


def test_dcos_cni_l4lb(dcos_api_session: DcosApiSession) -> Any:
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
    cni_config_app = MarathonApp(
        marathon.Container.NONE, marathon.Network.HOST, host,
        app_name_fmt='/integration-test/cni-l4lb/config-{}')

    # Override the default test app command with a command to write the CNI
    # configuration.
    #
    # NOTE: We add the original command at the end of this command so that the task
    # stays alive for the test harness to make sure that the task got deployed.
    # Ideally we should be able to deploy one of tasks using the test harness
    # but that doesn't seem to be the case here.
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
        marathon.Container.MESOS, marathon.Network.USER, host,
        vip=server_vip_label, app_name_fmt='/integration-test/cni-l4lb/server-{}')
    log.info("Server application: {}".format(server_app.app))

    # Get the client app on the 'spartan-net' network.
    client_app = MarathonApp(
        marathon.Container.MESOS, marathon.Network.USER, host,
        network_name='spartan-net', app_name_fmt='/integration-test/cni-l4lb/client-{}')
    log.info("Client application: {}".format(client_app.app))

    try:
        # Launch the test application
        client_app.deploy(dcos_api_session)
        server_app.deploy(dcos_api_session)

        # Wait for the test application
        server_app.wait(dcos_api_session)
        client_app.wait(dcos_api_session)

        # NOTE(mainred): route from the pytest worker node to the client
        # application is not ensured, so it's better to use the IP address of
        # the agent deploying the client app and the mapping port instead
        client_host, client_port = client_app.hostport(dcos_api_session)
        # Check linux kernel version
        uname = ensure_routable('uname -r', client_host, client_port, json_output=False)
        if '3.10.0-862' <= uname < '3.10.0-898':
            return pytest.skip('See https://bugzilla.redhat.com/show_bug.cgi?id=1572983')

        # Change the client command task to do a curl on the server we just deployed.
        cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}/test_uuid'.format(server_vip_addr)

        assert ensure_routable(cmd, client_host, client_port)['test_uuid'] == server_app.uuid
    finally:
        server_app.purge(dcos_api_session)
        client_app.purge(dcos_api_session)


def enum2str(value: Any) -> str:
    return str(value).split('.')[-1].lower()


def net2str(value: Any, ipv6: bool) -> str:
    return enum2str(value) if not ipv6 else 'ipv6'


@retrying.retry(wait_fixed=2000,
                stop_max_delay=100 * 2000,
                retry_on_exception=lambda x: True)
def test_dcos_net_cluster_identity(dcos_api_session: DcosApiSession) -> None:
    cluster_id = 'minuteman'  # default

    expanded_config = test_helpers.get_expanded_config()
    if expanded_config['dcos_net_cluster_identity'] == 'true':
        with open('/var/lib/dcos/cluster-id') as f:
            cluster_id = "'{}'".format(f.readline().rstrip())

    argv = ['sudo', '/opt/mesosphere/bin/dcos-net-env', 'eval', 'erlang:get_cookie().']
    cookie = subprocess.check_output(argv, stderr=subprocess.STDOUT).decode('utf-8').rstrip()

    assert cluster_id == cookie, "cluster_id: {}, cookie: {}".format(cluster_id, cookie)


@pytest.mark.parametrize('container', list(marathon.Container))
def test_calico_container_ip_in_network_cidr(container: marathon.Container, dcos_api_session: DcosApiSession) -> None:
    expanded_config = test_helpers.get_expanded_config()
    network_cidr = expanded_config["calico_network_cidr"]

    app = MarathonApp(
        container, marathon.Network.USER, network_name="calico",
        app_name_fmt='/integration-test/calico-cidr/{}')
    log.info("application: {}".format(app.app))

    try:
        app.deploy(dcos_api_session)
        app.wait(dcos_api_session)
        contain_ip_address, _ = app.hostport(dcos_api_session)
        assert IPv4Address(contain_ip_address) in IPv4Network(network_cidr)
    finally:
        app.purge(dcos_api_session)


def test_calico_cni_long_label(dcos_api_session: DcosApiSession) -> None:
    app = MarathonApp(
        marathon.Container.DOCKER,
        marathon.Network.USER,
        network_name="calico",
        app_name_fmt='/integration-test/calico-cni-long-label/app-path-longer-than-63-characters/{}')
    log.info("application: {}".format(app.app))

    try:
        app.deploy(dcos_api_session)
        app.wait(dcos_api_session)
        # We just need to wait until app is healthy
    finally:
        app.purge(dcos_api_session)
