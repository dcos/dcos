# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""All the code relevant for reflecting mocker, both Unix Socket and TCP/IP based"""

import logging

from mocker.endpoints.basehandler import BaseHTTPRequestHandler
from mocker.endpoints.generic import TcpIpHttpEndpoint, UnixSocketHTTPEndpoint

# pylint: disable=C0103
log = logging.getLogger(__name__)


# pylint: disable=R0903
class ReflectingHTTPRequestHandler(BaseHTTPRequestHandler):
    """A request hander class implementing sending back all the headers/request
    parameters,etc... back to the client.
    """
    def _calculate_response(self, base_path, url_args, body_args=None):
        """Gather all the request data into single dict and prepare it for
        sending it to the client for inspection, irrespective of the request
        URI.

        Please refer to the description of the BaseHTTPRequestHandler class
        method with the same name for details on the arguments and return value
        of this method.
        """
        return self._reflect_request(base_path, url_args, body_args)


# pylint: disable=R0903,C0103
class ReflectingTcpIpEndpoint(TcpIpHttpEndpoint):
    """ReflectingTcpIpEndpoint is just a plain TCP/IP endpoint with a
       request handler that pushes back request data to the client."""
    def __init__(self, port, ip='', keyfile=None, certfile=None):
        super().__init__(ReflectingHTTPRequestHandler, port, ip, keyfile, certfile)


# pylint: disable=R0903
class ReflectingUnixSocketEndpoint(UnixSocketHTTPEndpoint):
    """ReflectingUnixSocketEndpoint is just a plain Unix Socket endpoint with a
       request handler that pushes back request data to the client."""
    def __init__(self, path, keyfile=None, certfile=None):
        super().__init__(ReflectingHTTPRequestHandler, path, keyfile, certfile)
