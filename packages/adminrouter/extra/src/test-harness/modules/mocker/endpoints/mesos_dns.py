# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""MesosDNS mock endpoint"""

import copy
import logging
import re

from exceptions import EndpointException
from mocker.endpoints.recording import (
    RecordingHTTPRequestHandler,
    RecordingTcpIpEndpoint,
)

# pylint: disable=C0103
log = logging.getLogger(__name__)


# pylint: disable=R0903
class MesosDnsHTTPRequestHandler(RecordingHTTPRequestHandler):
    """Request handler that mimics MesosDNS

       Depending on how it was set up, it will respond with different SRV
       entries for preset services.
    """
    SRV_QUERY_REGEXP = re.compile('^/v1/services/_([^_]+)._tcp.marathon.mesos$')

    def _calculate_response(self, base_path, url_args, body_args=None):
        """Reply with the currently set mock-reply for given SRV record query.

        Please refer to the description of the BaseHTTPRequestHandler class
        for details on the arguments and return value of this method.

        Raises:
            EndpointException: request URL path is unsupported
        """

        match = self.SRV_QUERY_REGEXP.search(base_path)
        if match:
            return self.__srv_permissions_request_handler(match.group(1))

        raise EndpointException(
            code=500,
            content="Path `{}` is not supported yet".format(base_path))

    def __srv_permissions_request_handler(self, srvid):
        """Calculate reply for given service-ID

        Arguments:
            srvid (string): service ID to reply to"""
        ctx = self.server.context

        if srvid not in ctx.data['services']:
            raise EndpointException(
                code=500,
                content="Service `{}` is unknown".format(srvid))

        blob = self._convert_data_to_blob(ctx.data['services'][srvid])
        return 200, 'application/json', blob


def create_srv_entry(srv_name, ip, port):
    """Create a SRV entry basing on the supplied data

    Arguments:
        srv_name (string): service ID that the new SRV-entry should represent
        port (string): TCP/IP port that the new slave should pretend to listen on
        ip (string): IP address that the new slave hould pretend to listen on

    Returns:
        SRV entry dict mimicing the one returned by MesosDNS
    """
    res = {}
    res['service'] = "_{}._tcp.marathon.mesos".format(srv_name)
    res['host'] = "{}-74b1w-s1.marathon.mesos.".format(srv_name)
    res['ip'] = ip
    res['port'] = port

    return res

EMPTY_SRV = {
    "scheduler-alwaysthere": [
        {
            "service": "",
            "host": "",
            "ip": "",
            "port": "",
        }
    ],
}

SCHEDULER_SRV_ALWAYSTHERE = {
    "scheduler-alwaysthere": [
        create_srv_entry("scheduler-alwaysthere", "127.0.0.1", 16000),
        create_srv_entry("scheduler-alwaysthere", "127.0.0.1", 16002),
    ],
}
SCHEDULER_SRV_ALWAYSTHERE_DIFFERENTPORT = {
    "scheduler-alwaysthere": [
        create_srv_entry("scheduler-alwaysthere", "127.0.0.15", 16001),
        create_srv_entry("scheduler-alwaysthere", "127.0.0.1", 16002),
    ],
}
SCHEDULER_SRV_ALWAYSTHERE_NEST1 = {
    "nest2.nest1.scheduler-alwaysthere": [
        create_srv_entry("nest2.nest1.scheduler-alwaysthere", "127.0.0.1", 18000),
        create_srv_entry("nest2.nest1.scheduler-alwaysthere", "127.0.0.1", 16002),
    ],
}
SCHEDULER_SRV_ALWAYSTHERE_NEST2 = {
    "nest1.scheduler-alwaysthere": [
        create_srv_entry("nest1.scheduler-alwaysthere", "127.0.0.1", 17000),
        create_srv_entry("nest1.scheduler-alwaysthere", "127.0.0.1", 16002),
    ],
}

INITIAL_SRVDATA = {}
INITIAL_SRVDATA.update(SCHEDULER_SRV_ALWAYSTHERE)
INITIAL_SRVDATA.update(SCHEDULER_SRV_ALWAYSTHERE_NEST1)
INITIAL_SRVDATA.update(SCHEDULER_SRV_ALWAYSTHERE_NEST2)


# pylint: disable=R0903,C0103
class MesosDnsEndpoint(RecordingTcpIpEndpoint):
    """An endpoint that mimics DC/OS MesosDNS"""
    def __init__(self, port, ip=''):
        super().__init__(port, ip, MesosDnsHTTPRequestHandler)
        self.__context_init()

    def reset(self, *_):
        """Reset the endpoint to the default/initial state."""
        with self._context.lock:
            super().reset()
            self.__context_init()

    def set_srv_response(self, srvs):
        """Change the endpoint output so that it responds with a non-default
           MesosDNS srv node.
        """
        with self._context.lock:
            self._context.data["services"] = srvs

    def __context_init(self):
        """Helper function meant to initialize all the data relevant to this
           particular type of endpoint"""
        self._context.data["services"] = copy.deepcopy(INITIAL_SRVDATA)
