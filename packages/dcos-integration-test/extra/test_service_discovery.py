import collections
import logging

import socket

import pytest
import requests
import retrying

from test_helpers import dcos_config

from test_util.marathon import get_test_app, get_test_app_in_docker

DNS_ENTRY_UPDATE_TIMEOUT = 60  # in seconds


def _service_discovery_test(cluster, docker_network_bridge):
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
    mesos-dns to catch up with changes in the cluster.

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
    app_definition, test_uuid = get_test_app_in_docker(ip_per_container=False)

    if not docker_network_bridge:
        # TODO(cmaloney): This is very hacky to make PORT0 on the end instead of 9080...
        app_definition['cmd'] = app_definition['cmd'][:-4] + '$PORT0'
        app_definition['container']['docker']['network'] = 'HOST'
        del app_definition['container']['docker']['portMappings']
        app_definition['portDefinitions'] = [{
            "protocol": "tcp",
            "port": 0,
            "name": "test"
        }]

    app_definition['instances'] = 2

    assert len(cluster.slaves) >= 2, "Test requires a minimum of two agents"

    app_definition["constraints"] = [["hostname", "UNIQUE"], ]

    with cluster.marathon.deploy_and_cleanup(app_definition) as service_points:
        # Verify if Mesos-DNS agrees with Marathon:
        @retrying.retry(wait_fixed=1000,
                        stop_max_delay=DNS_ENTRY_UPDATE_TIMEOUT * 1000,
                        retry_on_result=lambda ret: ret is None,
                        retry_on_exception=lambda x: False)
        def _pool_for_mesos_dns():
            r = cluster.get('/mesos_dns/v1/services/_{}._tcp.marathon.mesos'.format(
                app_definition['id'].lstrip('/')))
            assert r.status_code == 200

            r_data = r.json()
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
        if len(cluster.slaves) >= 2:
            # When len(slaves)==1, we are connecting through docker-proxy using
            # docker0 interface ip. This makes this assertion useless, so we skip
            # it and rely on matching test uuid between containers only.
            assert r_data['my_ip'] == service_points[0].host


# There are several combinations we have to try of the way that Navstar DNS records are
# generated:
#
# Containerizers:
# -Mesos
# -Docker
#
# Network type:
# -Bridged
# -Host
# -Overlay
#
# Record type:
# -Container IP
# -Agent IP
# -Auto IP
#
# More info can be found here: https://dcos.io/docs/1.8/usage/service-discovery/dns-overview/
DNSAddresses = collections.namedtuple("DNSAddresses", ["container", "agent", "auto"])
MarathonAddresses = collections.namedtuple("MarathonAddresses", ["host", "container"])


def get_ipv4_addresses(hostname):
    res = socket.getaddrinfo(hostname, 0, family=socket.AF_INET, type=socket.SOCK_STREAM)
    return frozenset([sockaddr[0] for (family, type, proto, canonname, sockaddr) in res])


def get_dns_addresses_by_app_name(app_name):
    container_ip_name = '{}.marathon.containerip.dcos.thisdcos.directory'.format(app_name)
    agent_ip_name = '{}.marathon.agentip.dcos.thisdcos.directory'.format(app_name)
    auto_ip_name = '{}.marathon.auto.dcos.thisdcos.directory'.format(app_name)
    container_ips = get_ipv4_addresses(container_ip_name)
    agent_ips = get_ipv4_addresses(agent_ip_name)
    auto_ips = get_ipv4_addresses(auto_ip_name)
    return DNSAddresses(container_ips, agent_ips, auto_ips)


def get_marathon_addresses_by_service_points(service_points):
    marathon_host_addrs = frozenset([point.host for point in service_points])
    marathon_ip_addrs = frozenset([point.ip for point in service_points])
    return MarathonAddresses(marathon_host_addrs, marathon_ip_addrs)


def test_if_service_discovery_works_navstar_mesos_container_host_network(cluster):
    app_definition, test_uuid = get_test_app()
    with cluster.marathon.deploy_and_cleanup(app_definition) as service_points:
        marathon_addrs = get_marathon_addresses_by_service_points(service_points)
        assert marathon_addrs.host == marathon_addrs.container
        all_marathon_addrs = marathon_addrs.host

        @retrying.retry(wait_fixed=1000,
                        stop_max_delay=DNS_ENTRY_UPDATE_TIMEOUT * 1000,
                        retry_on_exception=lambda x: True)
        def _ensure_dns_converged():
            dns_addrs = get_dns_addresses_by_app_name(test_uuid)
            assert all_marathon_addrs == dns_addrs.agent
            assert all_marathon_addrs == dns_addrs.auto
            assert all_marathon_addrs == dns_addrs.container

        _ensure_dns_converged()


def test_if_service_discovery_works_navstar_mesos_container_overlay_network(cluster):
    app_definition, test_uuid = get_test_app(ip_per_container=True, custom_port=True)
    assert 'portDefinitions' not in app_definition  # Mesos cannot do port mapping yet
    app_definition['cmd'] += '9080'

    with cluster.marathon.deploy_and_cleanup(app_definition) as service_points:
        marathon_addrs = get_marathon_addresses_by_service_points(service_points)
        assert not frozenset.intersection(marathon_addrs.host, marathon_addrs.container)

        @retrying.retry(wait_fixed=1000,
                        stop_max_delay=DNS_ENTRY_UPDATE_TIMEOUT * 1000,
                        retry_on_exception=lambda x: True)
        def _ensure_dns_converged():
            dns_addrs = get_dns_addresses_by_app_name(test_uuid)
            assert marathon_addrs.host == dns_addrs.agent
            assert marathon_addrs.container == dns_addrs.auto
            assert marathon_addrs.container == dns_addrs.container

        _ensure_dns_converged()


def test_if_service_discovery_works_navstar_docker_container_bridge_network(cluster):
    app_definition, test_uuid = get_test_app_in_docker()
    with cluster.marathon.deploy_and_cleanup(app_definition) as service_points:
        marathon_addrs = get_marathon_addresses_by_service_points(service_points)
        assert not frozenset.intersection(marathon_addrs.host, marathon_addrs.container)

        @retrying.retry(wait_fixed=1000,
                        stop_max_delay=DNS_ENTRY_UPDATE_TIMEOUT * 1000,
                        retry_on_exception=lambda x: True)
        def _ensure_dns_converged():
            dns_addrs = get_dns_addresses_by_app_name(test_uuid)
            assert marathon_addrs.host == dns_addrs.agent
            assert marathon_addrs.container == dns_addrs.auto
            assert marathon_addrs.container == dns_addrs.container

        _ensure_dns_converged()


def test_if_service_discovery_works_docker_bridged_network(cluster):
    return _service_discovery_test(cluster, docker_network_bridge=True)


def test_if_service_discovery_works_docker_host_network(cluster):
    return _service_discovery_test(cluster, docker_network_bridge=False)


def test_if_search_is_working(cluster):
    """Test if custom set search is working.

    Verifies that a marathon app running on the cluster can resolve names using
    searching the "search" the cluster was launched with (if any). It also tests
    that absolute searches still work, and search + things that aren't
    sub-domains fails properly.

    The application being deployed is a simple http server written in python.
    Please check test_server.py for more details.
    """
    # Launch the app
    app_definition, test_uuid = get_test_app()
    with cluster.marathon.deploy_and_cleanup(app_definition) as service_points:
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

        # Check that result matches expectations for this cluster
        if dcos_config['dns_search']:
            assert r_data['search_hit_leader'] in cluster.masters
            assert r_data['always_hit_leader'] in cluster.masters
            assert r_data['always_miss'] == expected_error
        else:  # No dns search, search hit should miss.
            assert r_data['search_hit_leader'] == expected_error
            assert r_data['always_hit_leader'] in cluster.masters
            assert r_data['always_miss'] == expected_error
