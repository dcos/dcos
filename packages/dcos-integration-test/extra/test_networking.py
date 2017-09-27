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

import test_helpers
from dcos_test_utils import marathon

log = logging.getLogger(__name__)

# NOTE: linux kernel 3.10.0-327 (rh/centos 7.2) and 3.10.0-514 (rh/centos 7.3)
# drop outgoing vxlan tcp packets if the destination port is in the range
# from 14849 (0x3a01) to 15103 (0x3aff).
# For more information please see the following link:
# https://jira.mesosphere.com/browse/DCOS_OSS-1463?focusedCommentId=119792#comment-119792
# TODO: please check this port range on newer linux kernel
GLOBAL_PORT_POOL = collections.defaultdict(lambda: list(range(10000, 14849)) + list(range(15104, 32000)))


def unused_port(network):
    global GLOBAL_PORT_POOL
    return GLOBAL_PORT_POOL[network].pop(random.choice(range(len(GLOBAL_PORT_POOL[network]))))


def lb_enabled():
    return test_helpers.expanded_config['enable_lb'] == 'true'


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


def vip_app(container: marathon.Container, network: marathon.Network, host: str, vip: str):
    # user_net_port is only actually used for USER network because this cannot be assigned
    # by marathon
    if network in [marathon.Network.HOST, marathon.Network.BRIDGE]:
        # both of these cases will rely on marathon to assign ports
        return test_helpers.marathon_test_app(
            network=network,
            host_constraint=host,
            vip=vip,
            container_type=container,
            healthcheck_protocol=marathon.Healthcheck.MESOS_HTTP)
    elif network == marathon.Network.USER:
        return test_helpers.marathon_test_app(
            network=network,
            host_port=unused_port(marathon.Network.USER),
            host_constraint=host,
            vip=vip,
            container_type=container,
            healthcheck_protocol=marathon.Healthcheck.MESOS_HTTP)
    else:
        raise AssertionError('Unexpected network: {}'.format(network.value))


def generate_vip_app_permutations():
    """ Generate all possible network interface permutations for applying vips
    """
    return [(container, vip_net, proxy_net)
            for container in [marathon.Container.NONE, marathon.Container.MESOS, marathon.Container.DOCKER]
            for vip_net in [marathon.Network.USER, marathon.Network.BRIDGE, marathon.Network.HOST]
            for proxy_net in [marathon.Network.USER, marathon.Network.BRIDGE, marathon.Network.HOST]
            # only DOCKER containers support BRIDGE network
            if marathon.Network.BRIDGE not in (vip_net, proxy_net) or container == marathon.Container.DOCKER]


@pytest.mark.slow
@pytest.mark.skipif(
    not lb_enabled(),
    reason='Load Balancer disabled')
@pytest.mark.parametrize(
    'container,vip_net,proxy_net',
    generate_vip_app_permutations())
def test_vip(dcos_api_session,
             container: marathon.Container,
             vip_net: marathon.Network,
             proxy_net: marathon.Network):
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
    errors = 0
    tests = setup_vip_workload_tests(dcos_api_session, container, vip_net, proxy_net)
    for vip, hosts, cmd, origin_app, proxy_app in tests:
        log.info("Testing :: VIP: {}, Hosts: {}".format(vip, hosts))
        log.info("Remote command: {}".format(cmd))
        proxy_info = dcos_api_session.marathon.get('v2/apps/{}'.format(proxy_app['id'])).json()
        proxy_task_info = proxy_info['app']['tasks'][0]
        if proxy_net == marathon.Network.USER:
            proxy_host = proxy_task_info['ipAddresses'][0]['ipAddress']
            if container == marathon.Container.DOCKER:
                proxy_port = proxy_task_info['ports'][0]
            else:
                proxy_port = proxy_app['ipAddress']['discovery']['ports'][0]['number']
        else:
            proxy_host = proxy_task_info['host']
            proxy_port = proxy_task_info['ports'][0]
        try:
            ensure_routable(cmd, proxy_host, proxy_port)['test_uuid'] == origin_app['env']['DCOS_TEST_UUID']
        except Exception as e:
            log.error('Exception: {}'.format(e))
            errors = errors + 1
        finally:
            log.info('Purging application: {}'.format(origin_app['id']))
            dcos_api_session.marathon.delete('v2/apps/{}'.format(origin_app['id'])).raise_for_status()
            log.info('Purging application: {}'.format(proxy_app['id']))
            dcos_api_session.marathon.delete('v2/apps/{}'.format(proxy_app['id'])).raise_for_status()
    assert errors == 0


def setup_vip_workload_tests(dcos_api_session, container, vip_net, proxy_net):
    same_hosts = [True, False] if len(dcos_api_session.all_slaves) > 1 else [True]
    tests = [vip_workload_test(dcos_api_session, container, vip_net, proxy_net, named_vip, same_host)
             for named_vip in [True, False]
             for same_host in same_hosts]
    for vip, hosts, cmd, origin_app, proxy_app in tests:
        # We do not need the service endpoints because we have deterministically assigned them
        log.info('Starting apps :: VIP: {}, Hosts: {}'.format(vip, hosts))
        log.info("Origin app: {}".format(origin_app))
        dcos_api_session.marathon.post('v2/apps', json=origin_app).raise_for_status()
        log.info("Proxy app: {}".format(proxy_app))
        dcos_api_session.marathon.post('v2/apps', json=proxy_app).raise_for_status()
    for vip, hosts, cmd, origin_app, proxy_app in tests:
        log.info("Deploying apps :: VIP: {}, Hosts: {}".format(vip, hosts))
        log.info('Deploying origin app: {}'.format(origin_app['id']))
        wait_for_tasks_healthy(dcos_api_session, origin_app)
        log.info('Deploying proxy app: {}'.format(proxy_app['id']))
        wait_for_tasks_healthy(dcos_api_session, proxy_app)
        log.info('Apps are ready')
    return tests


def vip_workload_test(dcos_api_session, container, vip_net, proxy_net, named_vip, same_host):
    origin_host = dcos_api_session.all_slaves[0]
    proxy_host = dcos_api_session.all_slaves[0] if same_host else dcos_api_session.all_slaves[1]
    if named_vip:
        vip_port = unused_port('namedvip')
        vip = '/namedvip:{}'.format(vip_port)
        vipaddr = 'namedvip.marathon.l4lb.thisdcos.directory:{}'.format(vip_port)
    else:
        vip_port = unused_port('1.1.1.7')
        vip = '1.1.1.7:{}'.format(vip_port)
        vipaddr = vip
    cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}/test_uuid'.format(vipaddr)
    origin_app, origin_app_uuid = vip_app(container, vip_net, origin_host, vip)
    proxy_app, proxy_app_uuid = vip_app(container, proxy_net, proxy_host, None)
    # allow these apps to run on public slaves
    origin_app['acceptedResourceRoles'] = ['*', 'slave_public']
    proxy_app['acceptedResourceRoles'] = ['*', 'slave_public']
    hosts = list(set([origin_host, proxy_host]))
    return (vip, hosts, cmd, origin_app, proxy_app)


@retrying.retry(
    wait_fixed=5000,
    stop_max_delay=20 * 60 * 1000,
    retry_on_result=lambda res: res is False)
def wait_for_tasks_healthy(dcos_api_session, app_definition):
    info = dcos_api_session.marathon.get('v2/apps/{}'.format(app_definition['id'])).json()
    return info['app']['tasksHealthy'] == app_definition['instances']


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
    app_definition, test_uuid = test_helpers.marathon_test_app(
        healthcheck_protocol=marathon.Healthcheck.MESOS_HTTP,
        container_type=marathon.Container.DOCKER,
        network=marathon.Network.USER,
        host_port=9080)

    assert len(dcos_api_session.slaves) >= 2, 'IP Per Container tests require 2 private agents to work'

    app_definition['instances'] = 2
    app_definition['constraints'] = [['hostname', 'UNIQUE']]

    with dcos_api_session.marathon.deploy_and_cleanup(app_definition, check_health=True):
        service_points = dcos_api_session.marathon.get_app_service_endpoints(app_definition['id'])
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


@pytest.mark.skipif(not lb_enabled(), reason='Load Balancer disabled')
@pytest.mark.xfail(test_helpers.expanded_config.get('security') == 'strict',
                   reason='Cannot setup CNI config with EE strict mode enabled', strict=True)
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
    server_vip_port = unused_port('spartanvip')
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
    server['ipAddress']['networkName'] = 'dcos'

    log.info("Launching server with VIP:{} on network {}".format(server_vip_addr, server['ipAddress']['networkName']))

    try:
        dcos_api_session.marathon.deploy_app(server, check_health=False)
    except Exception as ex:
        raise AssertionError(
            "Couldn't launch server on 'dcos':{}".format(server['ipAddress']['networkName'])) from ex

    # Get the client app on the 'spartan-net' network.
    #
    # NOTE: Currently, we are creating the app-def by hand instead of relying
    # on the harness to create this app-def since the marathon harness does not
    # allow any port-mapping for CNI networks at this point.
    client_port = 9081
    client, test_uuid = test_helpers.marathon_test_app(
        container_type=marathon.Container.MESOS,
        healthcheck_protocol=marathon.Healthcheck.MESOS_HTTP,
        network=marathon.Network.USER,
        host_port=client_port,
        vip=server_vip,
        host_constraint=spartan_net_host)

    client["container"]["portMappings"] = [
        {
            'containerPort': client_port,
            'hostPort': client_port,
            'protocol': 'tcp',
            'name': 'http'
        }
    ]

    # Remove the `ipAddress` entry for DC/OS overlay.
    del client["ipAddress"]

    # Attach this container to the `spartan-net` network. We are using the v2
    # network API here.
    client["networks"] = [
        {
            "mode": "container",
            "name": "spartan-net"
        }
    ]

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
