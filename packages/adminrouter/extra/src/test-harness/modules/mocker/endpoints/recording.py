# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""All the code relevant to recording endpoint used by mocker.
"""

import copy
import logging
import time

from mocker.endpoints.basehandler import BaseHTTPRequestHandler
from mocker.endpoints.generic import TcpIpHttpEndpoint

# pylint: disable=C0103
log = logging.getLogger(__name__)


# pylint: disable=R0903
class RecordingHTTPRequestHandler(BaseHTTPRequestHandler):
    """A request hander class implementing recording all the requests&request
    data made to given endpoint.

    This class will most likely be inherited from and extended with some
    extra code that actually processes the requests because on itself
    it just returns some sample text.
    """
    def _record_request(self):
        """Store all the relevant data of the request into the endpoint context."""
        ctx = self.server.context

        res = {}
        res['method'] = self.command
        res['path'] = self.path
        res['headers'] = self.headers.items()
        res['request_version'] = self.request_version
        if self.headers.get('Content-Length') is not None:
            body_length = int(self.headers.get('Content-Length'))
            res['request_body'] = self.rfile.read(body_length).decode('utf-8')
        else:
            res['request_body'] = None
        res['request_time'] = time.time()

        with ctx.lock:
            ctx.data['requests'].append(res)
        msg_fmt = "[Endpoint `%s`] Request recorded: `%s`"
        log.debug(msg_fmt, ctx.data['endpoint_id'], res)

    def _process_commands(self, blob):
        """Process all the endpoint configuration and execute things that
           user requested.

        Please refer to the description of the BaseHTTPRequestHandler class
        for details on the arguments of this method.
        """
        ctx = self.server.context

        if ctx.data["record_requests"]:
            self._record_request()
            # Recording does not end the request processing, so we do not
            # return anything here

        if ctx.data["encoded_response"]:
            msg_fmt = "Endpoint `%s` sending encoded response `%s` as requested"
            log.debug(
                msg_fmt, ctx.data['endpoint_id'], ctx.data["encoded_response"])
            self._finalize_request(
                200, 'text/plain; charset=utf-8', ctx.data["encoded_response"])
            return True

        return super()._process_commands(blob)


# pylint: disable=C0103
class RecordingTcpIpEndpoint(TcpIpHttpEndpoint):
    """An endpoint that will record all the requests made to it.

    This endpoint can be used to test features that work in the background
    and are unavailable directly from the HTTP client context.

    In its current form, its functionality is incomplete/serves only some
    example data, it has to be extended/inherited from in order to serve as a
    mock.
    """
    def __init__(self, port, ip='', request_handler=RecordingHTTPRequestHandler):
        """Initialize new RecordingTcpIpEndpoint endpoint"""
        super().__init__(request_handler, port, ip)
        self.__context_init()

    def record_requests(self, *_):
        """Enable recording the requests data by the handler."""
        with self._context.lock:
            self._context.data["record_requests"] = True

    def get_recorded_requests(self, *_):
        """Fetch all the recorded requests data from the handler"""
        with self._context.lock:
            requests_list_copy = copy.deepcopy(self._context.data["requests"])

        return requests_list_copy

    def set_encoded_response(self, aux_data):
        """Make endpoint to respond with provided data without encoding data

        Arguments:
            aux_data (bytes): Encoded bytes array
        """
        with self._context.lock:
            self._context.data["encoded_response"] = aux_data

    def erase_recorded_requests(self, *_):
        """Fetch all the recorded requests data from the handler"""
        with self._context.lock:
            self._context.data["requests"] = list()

    def reset(self, *_):
        """Reset the endpoint to the default/initial state."""
        with self._context.lock:
            super().reset()
            self.__context_init()

    def __context_init(self):
        """Helper function meant to initialize all the data relevant to this
           particular type of endpoint"""
        self._context.data["record_requests"] = False
        self._context.data["requests"] = list()
        self._context.data["encoded_response"] = None
