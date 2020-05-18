import collections
import logging

import socket
from typing import Any, Optional

import pytest
import requests
import retrying
import test_helpers
from dcos_test_utils import marathon
from dcos_test_utils.dcos_api import DcosApiSession

__maintainer__ = 'urbanserj'
__contact__ = 'dcos-networking@mesosphere.io'

DNS_ENTRY_UPDATE_TIMEOUT = 60  # in seconds


def _service_discovery_test(dcos_api_session: DcosApiSession, docker_network_bridge: bool) -> None:
    """Service discovery integration test

    This test verifies if service discovery works, by comparing marathon data
    with information from mesos-dns and from containers themselves.

    This is achieved by deploying an application to marathon with two instances
    , and ["hostname", "UNIQUE"] constraint set. This should result in containers
    being deployed to two different slaves.

    The application being deployed is a simple http server written in python.
    Please check test_server.py for more details.

    Next thing is comparing the service points provided by marathon with those
    reported by mesos-dns. The tricky part here is that may take some time for
    mesos-dns to catch up with changes in the dcos_api_session.

    And finally, one of service points is verified in as-seen-by-other-containers
    fashion.

                        +------------------------+   +------------------------+
                        |          Slave 1       |   |         Slave 2        |
                        |                        |   |                        |
                        | +--------------------+ |   | +--------------------+ |
    +--------------+    | |                    | |   | |                    | |
    |              |    | |   App instance A   +------>+   App instance B   | |
    |   TC Agent   +<---->+                    | |   | |                    | |
    |              |    | |   "test server"    +<------+    "reflector"     | |
    +--------------+    | |                    | |   | |                    | |
                        | +--------------------+ |   | +--------------------+ |
                        +------------------------+   +------------------------+

    Code running on TC agent connects to one of the containers (let's call it
    "test server") and makes a POST request with IP and PORT service point of
    the second container as parameters (let's call it "reflector"). The test
    server in turn connects to other container and makes a "GET /reflect"
    request. The reflector responds with test server's IP as seen by it and
    the session UUID as provided to it by Marathon. This data is then returned
    to TC agent in response to POST request issued earlier.

    The test succeeds if test UUIDs of the test server, reflector and the test
    itself match and the IP of the test server matches the service point of that
    container as reported by Marathon.
    """

    # TODO(cmaloney): For non docker network bridge we should just do a mesos container.
    if docker_network_bridge:
        app_definition, test_uuid = test_helpers.marathon_test_app(
            container_type=marathon.Container.DOCKER,
            network=marathon.Network.BRIDGE,
            container_port=2020,
            host_port=9080)
    else:
        app_definition, test_uuid = test_helpers.marathon_test_app(container_type=marathon.Container.DOCKER)

    app_definition['instances'] = 2

    if len(dcos_api_session.slaves) < 2:
        pytest.skip("Service Discovery Tests require a minimum of two agents.")

    app_definition["constraints"] = [["hostname", "UNIQUE"], ]

    with dcos_api_session.marathon.deploy_and_cleanup(app_definition):
        service_points = dcos_api_session.marathon.get_app_service_endpoints(app_definition['id'])

        # Verify if Mesos-DNS agrees with Marathon:
        @retrying.retry(wait_fixed=1000,
                        stop_max_delay=DNS_ENTRY_UPDATE_TIMEOUT * 1000,
                        retry_on_result=lambda ret: ret is None,
                        retry_on_exception=lambda x: False)
        def _pool_for_mesos_dns() -> Optional[dict]:
            r = dcos_api_session.get('/mesos_dns/v1/services/_{}._tcp.marathon.mesos'.format(
                app_definition['id'].lstrip('/')))
            assert r.status_code == 200

            r_data = r.json()  # type: dict
            if r_data == [{'host': '', 'port': '', 'service': '', 'ip': ''}] or len(r_data) < len(service_points):
                logging.info("Waiting for Mesos-DNS to update entries")
                return None
            else:
                logging.info("Mesos-DNS entries have been updated!")
                return r_data

        try:
            r_data = _pool_for_mesos_dns()
        except retrying.RetryError:
            msg = "Mesos DNS has failed to update entries in {} seconds."
            pytest.fail(msg.format(DNS_ENTRY_UPDATE_TIMEOUT))

        marathon_provided_servicepoints = sorted((x.host, x.port) for x in service_points)
        mesosdns_provided_servicepoints = sorted((x['ip'], int(x['port'])) for x in r_data)
        assert marathon_provided_servicepoints == mesosdns_provided_servicepoints

        # Verify if containers themselves confirm what Marathon says:
        payload = {"reflector_ip": service_points[1].host,
                   "reflector_port": service_points[1].port}
        r = requests.post('http://{}:{}/your_ip'.format(
            service_points[0].host, service_points[0].port), payload)
        if r.status_code != 200:
            msg = "Test server replied with non-200 reply: '{status_code} {reason}. "
            msg += "Detailed explanation of the problem: {text}"
            pytest.fail(msg.format(status_code=r.status_code, reason=r.reason, text=r.text))

        r_data = r.json()
        assert r_data['reflector_uuid'] == test_uuid
        assert r_data['test_uuid'] == test_uuid
        if len(dcos_api_session.slaves) >= 2:
            # When len(slaves)==1, we are connecting through docker-proxy using
            # docker0 interface ip. This makes this assertion useless, so we skip
            # it and rely on matching test uuid between containers only.
            assert r_data['my_ip'] == service_points[0].host


# There are several combinations of Service Discovery Options we have to try:
#
# Containerizers:
# -Mesos
# -Docker
#
# Network type:
# -Bridged
# -Host
# -Overlay
# -Overlay with Port Mapping
#
# Record type:
# -Container IP
# -Agent IP
# -Auto IP
#
# More info can be found here: https://dcos.io/docs/1.8/usage/service-discovery/dns-overview/

DNSHost = 0
DNSPortMap = 1
DNSOverlay = 2

DNSAddresses = collections.namedtuple("DNSAddresses", ["container", "agent", "auto"])
MarathonAddresses = collections.namedtuple("MarathonAddresses", ["host", "container"])


def get_ipv4_addresses(hostname: Any) -> frozenset:
    res = socket.getaddrinfo(hostname, 0, family=socket.AF_INET, type=socket.SOCK_STREAM)
    return frozenset([sockaddr[0] for (family, type, proto, canonname, sockaddr) in res])


def get_dns_addresses_by_app_name(app_name: str) -> DNSAddresses:
    container_ip_name = '{}.marathon.containerip.dcos.thisdcos.directory'.format(app_name)
    agent_ip_name = '{}.marathon.agentip.dcos.thisdcos.directory'.format(app_name)
    auto_ip_name = '{}.marathon.autoip.dcos.thisdcos.directory'.format(app_name)
    container_ips = get_ipv4_addresses(container_ip_name)
    agent_ips = get_ipv4_addresses(agent_ip_name)
    auto_ips = get_ipv4_addresses(auto_ip_name)
    return DNSAddresses(container_ips, agent_ips, auto_ips)


def get_marathon_addresses_by_service_points(service_points: list) -> MarathonAddresses:
    marathon_host_addrs = frozenset([point.host for point in service_points])
    marathon_ip_addrs = frozenset([point.ip for point in service_points])
    return MarathonAddresses(marathon_host_addrs, marathon_ip_addrs)


def get_dcos_dns_records() -> Optional[dict]:
    response = requests.get('http://127.0.0.1:62080/v1/records')
    if response.status_code != 200:
        return None
    data = response.json()  # type: Optional[dict]
    return data


def assert_service_discovery(dcos_api_session: DcosApiSession, app_definition: Any, net_types: list) -> None:
    """
    net_types: List of network types: DNSHost, DNSPortMap, or DNSOverlay
    """

    with dcos_api_session.marathon.deploy_and_cleanup(app_definition):
        service_points = dcos_api_session.marathon.get_app_service_endpoints(app_definition['id'])
        marathon_addrs = get_marathon_addresses_by_service_points(service_points)

        if DNSHost in net_types:
            assert marathon_addrs.host == marathon_addrs.container
        else:
            assert not frozenset.intersection(marathon_addrs.host, marathon_addrs.container)

        @retrying.retry(wait_fixed=1000,
                        stop_max_delay=DNS_ENTRY_UPDATE_TIMEOUT * 1000,
                        retry_on_exception=lambda x: True)
        def _ensure_dns_converged() -> None:
            app_name = app_definition['id']
            try:
                dns_addrs = get_dns_addresses_by_app_name(app_name)
            except socket.gaierror as err:
                records = get_dcos_dns_records()
                logging.info("dcos-dns records: {}".format(records))
                raise err
            asserted = False
            if len(net_types) == 2:
                if (DNSOverlay in net_types) and (DNSPortMap in net_types):
                    assert marathon_addrs.host == dns_addrs.agent
                    assert marathon_addrs.host == dns_addrs.auto
                    assert marathon_addrs.container == dns_addrs.container
                    asserted = True
            if len(net_types) == 1:
                if DNSOverlay in net_types:
                    assert marathon_addrs.host == dns_addrs.agent
                    assert marathon_addrs.container == dns_addrs.auto
                    assert marathon_addrs.container == dns_addrs.container
                    asserted = True
                if DNSPortMap in net_types:
                    assert marathon_addrs.host == dns_addrs.agent
                    assert marathon_addrs.host == dns_addrs.auto
                    assert marathon_addrs.container == dns_addrs.container
                    asserted = True
                if DNSHost in net_types:
                    assert marathon_addrs.host == dns_addrs.agent
                    assert marathon_addrs.host == dns_addrs.auto
                    assert marathon_addrs.host == dns_addrs.container
                    asserted = True
            if not asserted:
                raise AssertionError("Not a valid dcos-net DNS combo")

        _ensure_dns_converged()


def test_service_discovery_mesos_host(dcos_api_session: DcosApiSession) -> None:
    app_definition, test_uuid = test_helpers.marathon_test_app(
        container_type=marathon.Container.MESOS, healthcheck_protocol=marathon.Healthcheck.HTTP)

    assert_service_discovery(dcos_api_session, app_definition, [DNSHost])


def test_service_discovery_mesos_overlay(dcos_api_session: DcosApiSession) -> None:
    app_definition, test_uuid = test_helpers.marathon_test_app(
        container_type=marathon.Container.MESOS,
        healthcheck_protocol=marathon.Healthcheck.MESOS_HTTP,
        network=marathon.Network.USER)

    assert_service_discovery(dcos_api_session, app_definition, [DNSOverlay])


def test_service_discovery_docker_host(dcos_api_session: DcosApiSession) -> None:
    app_definition, test_uuid = test_helpers.marathon_test_app(
        container_type=marathon.Container.DOCKER,
        network=marathon.Network.HOST)
    assert_service_discovery(dcos_api_session, app_definition, [DNSHost])


def test_service_discovery_docker_bridge(dcos_api_session: DcosApiSession) -> None:
    app_definition, test_uuid = test_helpers.marathon_test_app(
        container_type=marathon.Container.DOCKER,
        network=marathon.Network.BRIDGE,
        container_port=2020,
        host_port=9080)
    assert_service_discovery(dcos_api_session, app_definition, [DNSPortMap])


def test_service_discovery_docker_overlay(dcos_api_session: DcosApiSession) -> None:
    app_definition, test_uuid = test_helpers.marathon_test_app(
        container_type=marathon.Container.DOCKER,
        network=marathon.Network.USER)
    assert_service_discovery(dcos_api_session, app_definition, [DNSOverlay])


def test_service_discovery_docker_overlay_port_mapping(dcos_api_session: DcosApiSession) -> None:
    app_definition, test_uuid = test_helpers.marathon_test_app(
        container_type=marathon.Container.DOCKER,
        healthcheck_protocol=marathon.Healthcheck.MESOS_HTTP,
        network=marathon.Network.USER,
        host_port=9080)
    assert_service_discovery(dcos_api_session, app_definition, [DNSOverlay, DNSPortMap])


def test_service_discovery_docker_bridged_network(dcos_api_session: DcosApiSession) -> None:
    return _service_discovery_test(dcos_api_session, docker_network_bridge=True)


def test_service_discovery_docker_host_network(dcos_api_session: DcosApiSession) -> None:
    return _service_discovery_test(dcos_api_session, docker_network_bridge=False)


def test_if_search_is_working(dcos_api_session: DcosApiSession) -> None:
    """Test if custom set search is working.

    Verifies that a marathon app running on the dcos_api_session can resolve names using
    searching the "search" the dcos_api_session was launched with (if any). It also tests
    that absolute searches still work, and search + things that aren't
    sub-domains fails properly.

    The application being deployed is a simple http server written in python.
    Please check test_server.py for more details.
    """
    # Launch the app
    app_definition, test_uuid = test_helpers.marathon_test_app()
    with dcos_api_session.marathon.deploy_and_cleanup(app_definition):
        service_points = dcos_api_session.marathon.get_app_service_endpoints(app_definition['id'])
        # Get the status
        r = requests.get('http://{}:{}/dns_search'.format(service_points[0].host,
                                                          service_points[0].port))
        if r.status_code != 200:
            msg = "Test server replied with non-200 reply: '{0} {1}. "
            msg += "Detailed explanation of the problem: {2}"
            pytest.fail(msg.format(r.status_code, r.reason, r.text))

        r_data = r.json()

        # Make sure we hit the app we expected
        assert r_data['test_uuid'] == test_uuid

        expected_error = {'error': '[Errno -2] Name or service not known'}

        # Check that result matches expectations for this dcos_api_session
        expanded_config = test_helpers.get_expanded_config()
        if expanded_config['dns_search']:
            assert r_data['search_hit_leader'] in dcos_api_session.masters
            assert r_data['always_hit_leader'] in dcos_api_session.masters
            assert r_data['always_miss'] == expected_error
        else:  # No dns search, search hit should miss.
            assert r_data['search_hit_leader'] == expected_error
            assert r_data['always_hit_leader'] in dcos_api_session.masters
            assert r_data['always_miss'] == expected_error
