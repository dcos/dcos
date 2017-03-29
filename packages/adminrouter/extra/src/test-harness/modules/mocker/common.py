# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""
Shared management code for DC/OS mocks used by AR instances, both EE and Open.
"""

import concurrent.futures
import logging

from mocker.endpoints.reflectors import (
    ReflectingTcpIpEndpoint,
    ReflectingUnixSocketEndpoint,
)
from mocker.endpoints.mesos import MesosEndpoint
from mocker.endpoints.marathon import MarathonEndpoint

log = logging.getLogger(__name__)


class MockerBase:
    """This class represents mocking behaviour shared between both EE and Open
       repositories.

    It should not be instantiated directly but instead inheriting classes should
    override/extend it's methods.
    """
    _endpoints = None

    def _register_endpoints(self, endpoints):
        """Register given endpoints list with the mock

        This method registers all the endpoints that are going to be managed
        by this Mocker instance.

        Args:
            endpoints (object: [EndpointA, EndpointB,...]): list of endpoints
                that should be registered
        """
        self._endpoints = {}
        for endpoint in endpoints:
            log.info("Registering endpoint `%s`", endpoint.id)
            assert endpoint.id not in self._endpoints
            self._endpoints[endpoint.id] = endpoint

    @staticmethod
    def _create_common_endpoints():
        """Helper function that takes care of creating/instantiating all the
           endpoints that are common for both EE and Open repositories"""
        res = []

        # pkgpanda endpoint
        res.append(ReflectingUnixSocketEndpoint('/run/dcos/pkgpanda-api.sock'))
        # exhibitor
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.1', port=8181))
        # Mesos masters
        res.append(MesosEndpoint(ip='127.0.0.2', port=5050))
        res.append(MesosEndpoint(ip='127.0.0.3', port=5050))
        # Marathon instances running on the masters
        res.append(MarathonEndpoint(ip='127.0.0.1', port=8080))
        res.append(MarathonEndpoint(ip='127.0.0.2', port=8080))
        # cosmos
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.1', port=7070))
        # navstar
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.1', port=62080))
        # Mesos agents:
        # - plain/without TLS
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.2', port=15001))
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.3', port=15002))
        # - TLS version. It's used for testing e.g. DEFAULT_SCHEME variable
        # where AR is connecting to the upstream Mesos Agent using TLS.
        # 127.0.0.1 address stems from certificate names matching.
        res.append(ReflectingTcpIpEndpoint(
            ip='127.0.0.1',
            port=15401,
            certfile='/run/dcos/pki/tls/certs/adminrouter.crt',
            keyfile='/run/dcos/pki/tls/private/adminrouter.key'))
        # slave3
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.4', port=15003))
        # Slave AR 1
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.2', port=61001))
        # Slave AR 2
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.3', port=61001))
        # task /nginx-alwaysthere
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.1', port=16000))
        # task /nginx-enabled
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.1', port=16001))
        # other Admin Router Masters, used i.e. during Marathon leader testing
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.2', port=80))
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.3', port=80))
        res.append(ReflectingTcpIpEndpoint(
            ip='127.0.0.4',
            port=443,
            certfile='/run/dcos/pki/tls/certs/adminrouter.crt',
            keyfile='/run/dcos/pki/tls/private/adminrouter.key'))
        # metrics endpoint
        res.append(ReflectingUnixSocketEndpoint('/run/dcos/dcos-metrics-master.sock'))
        # log endpoint
        res.append(ReflectingUnixSocketEndpoint('/run/dcos/dcos-log.sock'))
        # DC/OS history service
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.2', port=15055))
        # Mesos DNS
        res.append(ReflectingTcpIpEndpoint(ip='127.0.0.1', port=8123))
        # Metrics(agent):
        res.append(
            ReflectingUnixSocketEndpoint(path='/run/dcos/dcos-metrics-agent.sock'))
        # TODO - other endpoints common for all flavours go here...

        return res

    def __init__(self, extra_endpoints=None):
        """Initialize new MockerBase instance

        Args:
            extra_endpoints (obj: [EndpointA, EndpointB,...]): list of endpoints
                that are unique to the inheriting class/represent specific behaviour
                of given flavour
        """
        common_endpoints = self._create_common_endpoints()
        endpoints = common_endpoints + extra_endpoints
        self._register_endpoints(endpoints)

    def start(self):
        """Start all endpoints registered with this Mocker instance"""
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for endpoint in self._endpoints.values():
                executor.submit(endpoint.start)

    def stop(self):
        """Stop all endpoints registered with this Mocker instance.

        Usually called right before object destruction
        """
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for endpoint in self._endpoints.values():
                executor.submit(endpoint.stop)

    def reset(self):
        """Reset all the endpoints to their initial state

        Used to make sure that all the tests start with fresh state/are not
        interfering with each other through Mocker
        """
        for endpoint in self._endpoints.values():
            endpoint.reset()

    def send_command(self, endpoint_id, func_name, aux_data=None):
        """Reconfigure endpoint manager by Mocker

        This method reconfigures endpoint previously started by Mocker. The
        reconfiguration is basically calling method `func_name` belonging to
        endpoint `endpoint_id` with data `aux_data`

        Args:
            endpoint_id (str): id of the endpoint to reconfigure
            func_name (str): name of the endpoint's function to call
            aux_data (str): auxilary data to pass to function

        Returns:
            Depends on the endpoint - it returns anything that endpoint returns.

        Raises:
            KeyError: endpoint with given id does not exists
            AttributeError: endpoint does not defines function `func_name`
        """
        endpoint = self._endpoints[endpoint_id]
        f = getattr(endpoint, func_name)

        return f(aux_data)
