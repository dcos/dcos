# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""All the code relevant for reflecting mocker, both Unix Socket and TCP/IP based"""

import logging

from cgi import parse_header, parse_multipart
from urllib.parse import parse_qs

from mocker.endpoints.generic import (
    TcpIpHttpEndpoint,
    UnixSocketHTTPEndpoint,
)
from mocker.endpoints.basehandler import (
    BaseHTTPRequestHandler,
)

# pylint: disable=C0103
log = logging.getLogger(__name__)


# pylint: disable=R0903
class ReflectingHTTPRequestHandler(BaseHTTPRequestHandler):
    """A request hander class implementing sending back all the headers/request
    parameters,etc... back to the client.
    """
    def _calculate_response(self, base_path, url_args, body_args=None):
        """Gather all the request data into single dict and prepare it for
        sending it to the client for inspection.

        Please refer to the description of the BaseHTTPRequestHandler class
        for details on the arguments and return value of this method.
        """
        ctx = self.server.context

        res = {}
        res['method'] = self.command
        res['path'] = self.path
        res['path_base'] = base_path
        res['headers'] = self.headers.items()
        res['request_version'] = self.request_version
        res['endpoint_id'] = ctx.data["endpoint_id"]
        res['args_url'] = url_args
        res['args_body'] = body_args
        blob = self._convert_data_to_blob(res)
        return blob

    def _parse_request_body(self):
        """Parse request body in order to extract arguments.

        This method recognizes both `multipart/form-data` and
        `multipart/form-data` encoded data. So the client can check how the
        Nginx in test behaves. It's based on: http://stackoverflow.com/a/4233452

        Returns:
            It returns a dictionary that contains all the parsed data. In case
            when body did not contain any arguments - an empty dict is returned.
        """
        if 'content-type' not in self.headers:
            return {}

        ctype, pdict = parse_header(self.headers['content-type'])
        if ctype == 'multipart/form-data':
            postvars = parse_multipart(self.rfile, pdict)
        elif ctype == 'application/x-www-form-urlencoded':
            # This should work (TM) basing on HTML5 spec:
            # Which default character encoding to use can only be determined
            # on a case-by-case basis, but generally the best character
            # encoding to use as a default is the one that was used to
            # encode the page on which the form used to create the payload
            # was itself found. In the absence of a better default,
            # UTF-8 is suggested.
            length = int(self.headers['content-length'])
            post_data = self.rfile.read(length).decode('utf-8')
            postvars = parse_qs(post_data,
                                keep_blank_values=1,
                                encoding="utf-8",
                                errors="strict",
                                )
        else:
            postvars = {}
        return postvars


# pylint: disable=R0903,C0103
class ReflectingTcpIpEndpoint(TcpIpHttpEndpoint):
    """ReflectingTcpIpEndpoint is just a plain TCP/IP endpoint with a
       request handler that pushes back request data to the client."""
    def __init__(self, port, ip=''):
        super().__init__(ReflectingHTTPRequestHandler, port, ip)


# pylint: disable=R0903
class ReflectingUnixSocketEndpoint(UnixSocketHTTPEndpoint):
    """ReflectingUnixSocketEndpoint is just a plain Unix Socket endpoint with a
       request handler that pushes back request data to the client."""
    def __init__(self, path):
        super().__init__(ReflectingHTTPRequestHandler, path)
