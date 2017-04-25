# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""Module that defines the behaviour common to all requests handlers used by mocker.
"""

import abc
import http.server
import json
import logging
import socket
import time
import traceback
from cgi import parse_header, parse_multipart
from urllib.parse import parse_qs, urlparse

from exceptions import EndpointException

# pylint: disable=C0103
log = logging.getLogger(__name__)


class BaseHTTPRequestHandler(http.server.BaseHTTPRequestHandler,
                             metaclass=abc.ABCMeta):
    """HTTP request handler base class that implements all common behaviour
       shared across mocker's request handlers.
    """
    @abc.abstractmethod
    def _calculate_response(self, base_path, url_args, body_args=None):
        """Calculate response basing on the request arguments.

        Methods overriding it should return a response body that reflects
        requests arguments and path.

        Args:
            base_path (str): request's path without query parameters
            url_args (dict): a dictionary containing all the query arguments
                encoded in request path
            body_args (dict): a dictionary containing all the arguments encoded
                in the body of the request

        Returns:
            A tuple which contains, in order:
                * HTTP status of the response
                * content type of the response
                * a bytes array, exactly as it should be send to the client.

        Raises:
            EndpointException: This exception signalizes that the normal
                processing of the request should be stopped, and the response
                with given status&content-encoding&body should be immediately
                sent.
        """
        pass

    def _reflect_request(self, base_path, url_args, body_args=None):
        """Gather all the request data into single dict and prepare it for
        sending it to the client for inspection.

        Please refer to the description of the _calculate_response method
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
        return 200, 'application/json', blob

    def _parse_request_body(self):
        """Parse request body in order to extract arguments.

        This method recognizes both `multipart/form-data` and
        `application/x-www-form-urlencoded` encoded data. So the client can
        check how the tested Nginx behaves with different kinds of params.
        It's based on: http://stackoverflow.com/a/4233452

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

    def _process_commands(self, blob):
        """Process all the endpoint configuration and execute things that
           user requested.

        Please check the Returns section to understand how chaining response
        handling/overriding this method look like.

        Arguments:
            blob (bytes array): data that is meant to be sent to the client.

        Returns:
            True/False depending on whether response was handled by this method
            or not. Basing on it calling method determines if it should continue
            processing data.
        """
        ctx = self.server.context

        with ctx.lock:
            do_always_bork = ctx.data['always_bork']

            do_always_redirect = ctx.data['always_redirect']
            redirect_target = ctx.data['redirect_target']

            do_always_stall = ctx.data['always_stall']
            stall_time = ctx.data['stall_time']

        if do_always_stall:
            msg_fmt = "Endpoint `%s` waiting `%f` seconds as requested"
            log.debug(msg_fmt, ctx.data['endpoint_id'], stall_time)
            time.sleep(stall_time)
            # This does not end request processing

        if do_always_bork:
            msg_fmt = "Endpoint `%s` sending broken response as requested"
            log.debug(msg_fmt, ctx.data['endpoint_id'])
            blob = b"Broken response due to `always_bork` flag being set"
            self._finalize_request(500, 'text/plain; charset=utf-8', blob)
            return True

        if do_always_redirect:
            msg_fmt = "Endpoint `%s` sending redirect to `%s` as requested"
            log.debug(msg_fmt, ctx.data['endpoint_id'], redirect_target)
            headers = {"Location": redirect_target}
            self._finalize_request(307,
                                   'text/plain; charset=utf-8',
                                   blob,
                                   extra_headers=headers)
            return True

        return False

    def log_message(self, log_format, *args):
        """Just a patch to make Mockers Requests Handlers compatible with
           Unix Sockets.

        Method logs the request without source IP address/with hard-coded value
        of `unix-socket-connection` if the socket is a Unix Socket.

        Please check the http.server.BaseHTTPRequestHandler documentation
        for the meaning of the function arguments.
        """
        endpoint_id = self.server.context.data['endpoint_id']
        if self.server.address_family == socket.AF_UNIX:
            log.debug("[Endpoint: %s] %s - - [%s] %s\n",
                      endpoint_id,
                      "unix-socket-connection",
                      self.log_date_time_string(),
                      log_format % args)
        else:
            log.debug("[Endpoint: %s] %s - - [%s] %s\n",
                      endpoint_id,
                      self.address_string(),
                      self.log_date_time_string(),
                      log_format % args)

    def _finalize_request(self, code, content_type, blob, extra_headers=None):
        """A helper function meant to abstract sending request to client

        Arguments:
            code (int): HTTP response code to send
            content_type (string): HTTP content type value of the response
            blob (b''): data to send to the client in the body of the request
            extra_headers (dict): extra headers that should be set in the reply
        """
        try:
            self.send_response(code)
            self.send_header('Content-type', content_type)
            if extra_headers is not None:
                for name, val in extra_headers.items():
                    self.send_header(name, val)
            self.end_headers()

            self.wfile.write(blob)
        except BrokenPipeError:
            log.warn("Client already closed the connection, "
                     "aborting sending the response")

    @staticmethod
    def _convert_data_to_blob(data):
        """A helper function meant to simplify converting python objects to
           bytes arrays.

        Arguments:
            data: data to convert to b''. Can be anything as long as it's JSON
                serializable.

        Returns:
            A resulting byte sequence
        """
        return json.dumps(data,
                          indent=4,
                          sort_keys=True,
                          ensure_ascii=False,
                          ).encode('utf-8',
                                   errors='backslashreplace')

    def _parse_request_path(self):
        """Parse query arguments in the request path to dict.

        Returns:
            A tuple that contains a request path stripped of query arguments
            and a dict containing all the query arguments (if any).
        """
        parsed_url = urlparse(self.path)
        path_component = parsed_url.path
        query_components = parse_qs(parsed_url.query)
        return path_component, query_components

    def _unified_method_handler(self):
        """A unified entry point for all request types.

        This method is meant to be top level entry point for all requests.
        This class specifies only GET|POST for now, but other handlers can
        add request types if necessary.

        All query parameters are extracted (both from the uri and the body),
        and the handlers self._calculate_response method is called to produce
        a correct response. Handlers may terminate this workflow by raising
        EndpointException if necessary. All other exceptions are also caught and
        apart from being logged, are also send to the client in order to
        make debugging potential problems easier and failures more explicit.
        """
        try:
            path, url_args = self._parse_request_path()
            body_args = self._parse_request_body()
            status, content_type, blob = self._calculate_response(path, url_args, body_args)
        except EndpointException as e:
            self._finalize_request(e.code, e.content_type, e.reason)
        # Pylint, please trust me on this one ;)
        # pylint: disable=W0703
        except Exception:
            endpoint_id = self.server.context.data['endpoint_id']
            msg_fmt = ("Exception occurred while handling the request in "
                       "endpoint `%s`")
            log.exception(msg_fmt, endpoint_id)

            # traceback.format_exc() returns str, i.e. text, i.e. a sequence of
            # unicode code points. UTF-8 is a unicode-complete codec. That is,
            # any and all unicode code points can be encoded.
            blob = traceback.format_exc().encode('utf-8')
            self._finalize_request(500, 'text/plain; charset=utf-8', blob)
        else:
            request_handled = self._process_commands(blob)

            # No need to specify character encoding if type is json:
            # http://stackoverflow.com/a/9254967
            if not request_handled:
                self._finalize_request(status, content_type, blob)

    def do_GET(self):
        """Please check the http.server.BaseHTTPRequestHandler documentation
           for the method description.

        Worth noting is that GET request can also be a POST - can have both
        request path arguments and body arguments.
        http://stackoverflow.com/a/2064369
        """
        self._unified_method_handler()

    def do_POST(self):
        """Please check the http.server.BaseHTTPRequestHandler documentation
           for the method description.

        Worth noting is that GET request can also be a POST - can have both
        request path arguments and body arguments.
        http://stackoverflow.com/a/2064369
        """
        self._unified_method_handler()
