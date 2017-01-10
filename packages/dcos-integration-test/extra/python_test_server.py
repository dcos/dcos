#!/usr/bin/env python3
import getpass
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

LOG_LEVEL = logging.DEBUG
TEST_UUID_VARNAME = "DCOS_TEST_UUID"
TEST_DATA_CACHE = ""


class RequestProcessingException(Exception):
    """Processing of the request has failed

    This exception is used to signal that processing of the request has failed
    and that the client should be sent the response imediattelly. The response
    that should be sent is decribed by class attributes.

    Attributes:
        code: HTTP code that should be sent to client [int]
        reason: short description of the problem, will be put into status line
                of the HTTP response (yeah, let's break the RFC! :D)
        explanation: long explanation of the problem. Will be included in
                     response's body
    """
    def __init__(self, code, reason, explanation=''):
        """Inits RequestProcessingException with data used to build a reply to client"""
        self.code = code
        self.reason = reason
        self.explanation = explanation


def setup_logging():
    """Setup logging for the script"""
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)
    fmt = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    logger.addHandler(handler)


class TestHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        """Override logging settings of base class

        This method reformats standard request logging provided by the base
        class BaseHTTPRequestHandler and sends it to logger/formatter
        configured by the user during logging module initialization

        Args:
            fmt, args: just like base class
        """
        logging.info("REQ: {0} {1}".format(self.address_string(), fmt % args))

    def _send_reply(self, data):
        """Send reply to client in JSON format

        Send a successfull reply to the client, with reply data/body
        formatted/serialized as JSON. It also makes sure that headers are set
        right and JSON is formated in human-readable form.

        Args:
            data: free form data that should be serialized to JSON
        """
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        body_str = json.dumps(data, sort_keys=True, indent=4, separators=(',', ': '))
        bytes_arr = bytes(body_str, "utf-8")
        self.wfile.write(bytes_arr)

    def _handle_path_dns_search(self):
        """Respond to a dns resolution request with the dns results for a name"""

        def get_hostbyname_json(hostname):
            try:
                return socket.gethostbyname(hostname)
            except socket.gaierror as ex:
                return {"error": str(ex)}

        data = {
            "search_hit_leader": get_hostbyname_json("leader"),
            "always_miss": get_hostbyname_json("notasubdomainofmesos"),
            "always_hit_leader": get_hostbyname_json("leader.mesos"),
            "test_uuid": os.environ[TEST_UUID_VARNAME],
        }
        self._send_reply(data)

    def _handle_path_ping(self):
        """Respond to PING request with PONG reply"""
        data = {"pong": True}
        self._send_reply(data)

    def _handle_path_uuid(self):
        """Respond to request for UUID with servers test-sesion UUID"""
        data = {"test_uuid": os.environ[TEST_UUID_VARNAME]}
        self._send_reply(data)

    def _handle_path_reflect(self):
        """Respond to request for client's IP with it's as seen by the server"""
        data = {"test_uuid": os.environ[TEST_UUID_VARNAME],
                "request_ip": self.address_string()}
        self._send_reply(data)

    def _handle_path_signal_test_cache(self, set_data):
        """Use the sever to cache results from application runs"""
        global TEST_DATA_CACHE
        if set_data:
            TEST_DATA_CACHE = self.rfile.read(int(self.headers['Content-Length'])).decode()
        self._send_reply(TEST_DATA_CACHE)

    def parse_POST_headers(self):  # noqa: ignore=N802
        """Parse request's POST headers in utf8 aware way

        Returns:
            A dictionary with POST arguments mapped to it's keys/values
        """
        length = int(self.headers['Content-Length'])
        field_data = self.rfile.read(length).decode('utf-8')
        fields = urllib.parse.parse_qs(field_data)
        logging.debug("Request's POST arguments: {}".format(fields))
        return fields

    def _verify_path_your_ip_args(self, fields):
        """Verify /your_ip request's arguments

        Make sure that the POST arguments send by the client while requesting
        for /your_ip path are valid.

        Args:
            fields: decoded POST arguments sent by the client in the form of
                    dictionary

        Raises:
            RequestProcessingException: some/all arguments are missing and/or
                                        malformed. Request should be aborted.
        """
        if "reflector_ip" not in fields or "reflector_port" not in fields:
            raise RequestProcessingException(400, 'Reflector data missing',
                                             'Reflector IP and/or port has not '
                                             'been provided, so the request cannot '
                                             'be processed.')

        fields['reflector_ip'] = fields['reflector_ip'][0]
        fields['reflector_port'] = fields['reflector_port'][0]

        try:
            fields['reflector_port'] = int(fields['reflector_port'])
        except ValueError:
            msg = 'Reflector port "{}" is not an integer'
            raise RequestProcessingException(400, msg.format(fields['reflector_port']))

        try:
            socket.inet_aton(fields['reflector_ip'])
        except socket.error:
            msg = 'Reflector IP "{}" is invalid/not a proper ipv4'
            raise RequestProcessingException(400, msg.format(fields['reflector_ip']))

    def _query_reflector_for_ip(self, reflector_ip, reflector_port):
        """Ask the reflector to report server's IP address

        This method queries external reflector for server's IP address. It's done
        by sending a 'GET /reflect' request to a test_server running on some
        other messos slave. Please see the descripion of the '_handle_path_reflect'
        method for more details.

        Args:
            reflector_ip: IP where the test_server used as a reflector can be
                          found
            reflector_port: TCP port on which reflector listens for incomming
                            connections

        Raises:
            RequestProcessingException: server failed to communicate reflector,
                                        and the request that initiated the query
                                        should be aborted.
        """
        uri = 'http://{}:{}/reflect'.format(reflector_ip, reflector_port)

        try:
            r = requests.get(uri, timeout=1.0)
        except requests.Timeout as e:
            raise RequestProcessingException(500, 'Reflector timed out',
                                             "Reflector was unable to respond "
                                             "in timely manner: {}".format(e))
        except requests.RequestException as e:
            raise RequestProcessingException(500, 'Reflector connection error',
                                             "Unable to connect to reflector: "
                                             "{}".format(e))

        if r.status_code != 200:
            msg_short = 'Data fetch from reflector failed.'
            msg_detailed = 'Reflector responded with code: {}, response body: {}'
            reply_body = r.text.replace('\n', ' ')
            raise RequestProcessingException(500, msg_short,
                                             msg_detailed.format(r.status_code,
                                                                 reply_body))

        try:
            return r.json()
        except ValueError as e:
            raise RequestProcessingException(500, 'Malformed reflector response',
                                             "Reflectors response is not a "
                                             "valid JSON: {}".format(e))

    def _handle_path_your_ip(self):
        """Resspond to requests for server's IP address as seen by other cluster memebers

        Determine the server's address by quering external reflector (basically
        the same test_server, but different service endpoint), and repond to
        client with JSON hash containing test UUID's of the server, reflector,
        and IP address as reported by the reflector
        """
        form_data = self.parse_POST_headers()
        self._verify_path_your_ip_args(form_data)
        reflector_data = self._query_reflector_for_ip(form_data['reflector_ip'],
                                                      form_data['reflector_port'])

        data = {"reflector_uuid": reflector_data['test_uuid'],
                "test_uuid": os.environ[TEST_UUID_VARNAME],
                "my_ip": reflector_data['request_ip']}
        self._send_reply(data)

    def _handle_path_run_cmd(self):
        """Runs an arbitrary command, and returns the output along with the return code

        Sometimes there isn't enough time to write code
        """
        length = int(self.headers['Content-Length'])
        cmd = self.rfile.read(length).decode('utf-8')
        (status, output) = subprocess.getstatusoutput(cmd)
        data = {"status": status, "output": output}
        self._send_reply(data)

    def _handle_operating_environment(self):
        """Gets basic operating environment info (such as running user)"""
        self._send_reply({
            'username': getpass.getuser(),
            'uid': os.getuid()
        })

    def do_GET(self):  # noqa: ignore=N802
        """Mini service router handling GET requests"""
        # TODO(cmaloney): Alphabetize these.
        if self.path == '/ping':
            self._handle_path_ping()
        elif self.path == '/test_uuid':
            self._handle_path_uuid()
        elif self.path == '/reflect':
            self._handle_path_reflect()
        elif self.path == '/dns_search':
            self._handle_path_dns_search()
        elif self.path == '/signal_test_cache':
            self._handle_path_signal_test_cache(False)
        elif self.path == '/operating_environment':
            self._handle_operating_environment()
        else:
            self.send_error(404, 'Not found', 'Endpoint is not supported')

    def do_POST(self):  # noqa: ignore=N802
        """Mini service router handling POST requests"""
        if self.path == '/your_ip':
            try:
                self._handle_path_your_ip()
            except RequestProcessingException as e:
                logging.error("Request processing exception occured: "
                              "code: {}, reason: '{}', explanation: '{}'".format(
                                  e.code, e.reason, e.explanation))
                self.send_error(e.code, e.reason, e.explanation)
        elif self.path == '/signal_test_cache':
            self._handle_path_signal_test_cache(True)
        elif self.path == '/run_cmd':
            self._handle_path_run_cmd()
        else:
            self.send_error(404, 'Not found', 'Endpoint is not supported')


def _verify_environment():
    """Verify that the enviroment is sane and can be used by the test_server"""
    if TEST_UUID_VARNAME not in os.environ:
        logging.error("Uniq test ID is missing in env vars, aborting.")
        sys.exit(1)


def start_http_server(listen_port):
    """Start the test server

    This function makes sure that the environment is sane and signals are properly
    handled, and then launches a test server
    """
    _verify_environment()

    logging.info("HTTP server is starting, port: "
                 "{}, test-UUID: '{}'".format(listen_port, os.environ[TEST_UUID_VARNAME]))
    test_server = HTTPServer(('', listen_port), TestHTTPRequestHandler)

    def sigterm_handler(_signo, _stack_frame):
        test_server.server_close()
        logging.info("HTTP server is terminating")
        sys.exit(0)

    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)

    test_server.serve_forever()


def main():
    setup_logging()
    start_http_server(int(sys.argv[1]))


if __name__ == '__main__':
    main()
