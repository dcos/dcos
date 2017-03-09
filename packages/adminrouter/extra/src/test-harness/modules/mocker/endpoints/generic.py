# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""
Shared code for DC/OS endpoints mocks used by AR instances, both EE and Open.
"""

import abc
import http.server
import logging
import os
import socket
import socketserver
import ssl
import threading

# pylint: disable=C0103
log = logging.getLogger(__name__)


# Just a dict would be no good as we want to have threading lock initialization
# as well.
# pylint: disable=R0903
class EndpointContext():
    """An endpoint context that holds all the endpoint data together with
       threading lock that protects it."""
    data = None
    lock = None

    def __init__(self, initial_data=None):
        """Initialize EndpointContext object.

        This data is often manipulated by methods nested across
        inheritance chains, so we need to use RLock() instead of Lock().

        The need for the lock itself stems from the fact that very often certain
        keys of the context need to be manipulated at the same time/in synchronized
        manner.

        In some of the places, code relies on thread safety/atomicity of
        some of Python's expressions/statements:

            https://docs.python.org/3.6/faq/library.html#what-kinds-of-global-value-mutation-are-thread-safe

        This is why some of the operations on the EndpointContext dictionary
        are not protected by locks, esp. in case when it's only about fetching
        a single value from context dict or storing/appending one there.

        Args:
            initial_data (dict): initial data to initialize context with
        """
        self.lock = threading.RLock()
        if initial_data is not None:
            self.data = initial_data
        else:
            self.data = {}


class Endpoint(abc.ABC):
    """Endpoint base class, from which all Endpoints must inherit

       This class represents common behaviour shared across all endpoints,
       no matter the function or repository flavour (ee/open).

       Ever endpoint must by default serve GOOD/expected data, and only after
       changing it's state using it's methods, it may start serving something
       else and/or simulate error conditions.

       The state of the endpoint may be changed by tests/fixtures by executing
       Mocker's .send_command() method which in turn redirect the call to the
       correct endpoint call. For the sake of simplicity it is assumed that each
       such method will have well-defined interface:
        def do_something(self, aux_data=None):
            return result

        `aux_data` is a python dictionary that must provide all data required
            by function to execute. It can be None if such data is not required
        `result` can be anything that makes sense in particular function's case.
    """
    _context = None
    _httpd_thread = None
    _httpd = None

    def __init__(self, endpoint_id):
        """Initialize new Endpoint object

        Args:
            endpoint_id (str): ID of the endpoint that it should identify itself
                with
        """
        initial_data = {"always_bork": False,
                        "endpoint_id": endpoint_id,
                        "always_redirect": False,
                        "redirect_target": None,
                        "always_stall": False,
                        "stall_time": 0,
                        }
        self._context = EndpointContext(initial_data)

    @property
    def id(self):
        """Return ID of the endpoint"""
        return self._context.data['endpoint_id']

    def start(self):
        """Start endpoint's threaded httpd server"""
        log.debug("Starting endpoint `%s`", self.id)
        self._httpd_thread.start()
        self._httpd.startup_done.wait()

    def stop(self):
        """Perform cleanup of the endpoint threads

        This method should be used right before destroying the Endpoint object.
        It takes care of stopping internal httpd server.
        """
        log.debug("Stopping endpoint `%s`", self.id)
        self._httpd.shutdown()
        self._httpd_thread.join()

    def reset(self, aux_data=None):
        """Reset endpoint to the default/good state

        Args:
            aux_data (dict): unused, present only to satisfy the endpoint's
                method interface. See class description for details.
        """
        del aux_data
        log.debug("Resetting endpoint `%s`", self.id)
        # Locking is not really needed here as it is atomic op anyway,
        # but let's be consistent
        with self._context.lock:
            self._context.data['always_bork'] = False

            self._context.data['always_stall'] = False
            self._context.data['stall_time'] = 0

            self._context.data["always_redirect"] = False
            self._context.data["redirect_target"] = None

    def always_stall(self, aux_data=None):
        """Make endpoint always wait given time before answering the request

        Args:
            aux_data (numeric): time in seconds, as acepted by time.sleep()
                function
        """
        with self._context.lock:
            self._context.data["always_stall"] = True
            self._context.data["stall_time"] = aux_data

    def always_bork(self, aux_data=True):
        """Make endpoint always respond with an error

        Args:
            aux_data (dict): True or False, depending whether endpoint should
                always respond with errors or not.
        """
        self._context.data["always_bork"] = aux_data

    def always_redirect(self, aux_data=None):
        """Make endpoint always respond with a redirect

        Args:
            aux_data (str): target location for the redirect
        """
        with self._context.lock:
            self._context.data["always_redirect"] = True
            self._context.data["redirect_target"] = aux_data


class StatefullHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Base class for all endpoint-internal httpd servers.

    This class serves as a base for all internal httpd server, it's role is
    to pull in Threading mix-in and link Endpoint context to httpd itself,
    so that it's available in the httpd request handler through request's
    .server.context attribute.

    Worth noting that this is by default a TCP/IP server.

    It's based on:
    https://mail.python.org/pipermail/python-list/2012-March/621727.html
    """
    def __init__(self, context, *args, **kw):
        self.context = context
        self.startup_done = threading.Event()
        http.server.HTTPServer.__init__(self, *args, **kw)

        certfile = self.context.data['certfile']
        keyfile = self.context.data['keyfile']
        if certfile is not None and keyfile is not None:
            self.socket = ssl.wrap_socket(self.socket,
                                          keyfile=keyfile,
                                          certfile=certfile,
                                          server_side=True)

    def server_activate(self):
        super().server_activate()
        self.startup_done.set()


class TcpIpHttpEndpoint(Endpoint):
    """Base class for all endpoints that serve TCP/IP requests

        This class binds together HTTPd server code, http request handler and
        endpoint context to form a base class for all endpoints that serve
        TCP/IP traffic.
    """
    def __init__(self, handler_class, port, ip='', keyfile=None, certfile=None):
        """Initialize new TcpIpHttpEndpoint object

        Args:
            handler_class (obj): a request handler class that will be handling
                requests received by internal httpd server
            port (int): tcp port that httpd server will listen on
            ip (str): ip address that httpd server will listen on, by default
                listen on all addresses
        """
        if certfile is not None and keyfile is not None:
            endpoint_id = "https://{}:{}".format(ip, port)
        else:
            endpoint_id = "http://{}:{}".format(ip, port)
        super().__init__(endpoint_id)

        self._context.data['listen_ip'] = ip
        self._context.data['listen_port'] = port
        self._context.data['certfile'] = certfile
        self._context.data['keyfile'] = keyfile

        self._handler_class = handler_class

        self.__setup_httpd_thread(ip, port)

    def __setup_httpd_thread(self, ip, port):
        """Setup internal HTTPd server that this endpoints relies on to serve
           requests.
        """
        self._httpd = StatefullHTTPServer(self._context,
                                          (ip, port),
                                          self._handler_class)

        httpd_thread_name = "TcpIpHttpdThread-{}".format(self.id)
        self._httpd_thread = threading.Thread(target=self._httpd.serve_forever,
                                              name=httpd_thread_name)


class UnixSocketStatefulHTTPServer(StatefullHTTPServer):
    """Base class for all endpoint-internal httpd servers that listen on
       Unix socket.

    This class inherits from StatefullHTTPServer and mofies it's behaviour
    so that it's able to listen on Unix socket.

    Attributes:
        address_family: set only to override default value of the variable set
            in the http.server.HTTPServer class, must not be modified.
    """
    address_family = socket.AF_UNIX

    def server_bind(self):
        """Override default server socket bind behaviour to adapt it to
           serving on Unix socket.

        Please check the documentation of http.server.HTTPServer class for more
        details.
        """
        socketserver.TCPServer.server_bind(self)
        self.server_name = self.context.data['socket_path']
        self.server_port = 0

    def client_address(self):
        """Override default client_address method to adapt it to serving on Unix
        socket. Without it logging will break as Unix socket has no notion of
        the client's IP address.

        Please check the documentation of http.server.HTTPServer class for more
        details.
        """
        return (self.context.data['socket_path'], 0)


# http://stackoverflow.com/questions/21650370/setting-up-an-http-server-that-listens-over-a-file-socket
# https://docs.python.org/3.3/library/socketserver.html
class UnixSocketHTTPEndpoint(Endpoint):
    """Base class for all endpoints that serve requests on the Unix socket

        This class binds together HTTPd server code, http request handler and
        endpoint context to form a base class for all endpoints that serve
        Unix socket traffic.
    """
    def __init__(self, handler_class, path, keyfile=None, certfile=None):
        """Initialize new UnixSocketHTTPEndpoint object

        Args:
            handler_class (obj): a request handler class that will be handling
                requests received by internal httpd server
            path (str): Unix socket path, that internal httpd server will listen
                on
        """
        if certfile is not None and keyfile is not None:
            endpoint_id = "https://{}".format(path)
        else:
            endpoint_id = "http://{}".format(path)
        super().__init__(endpoint_id)

        self._context.data['socket_path'] = path
        self._context.data['certfile'] = certfile
        self._context.data['keyfile'] = keyfile

        self._handler_class = handler_class

        self.__cleanup_stale_socket(path)
        self.__setup_httpd_thread(path)

    @staticmethod
    def __cleanup_stale_socket(socket_path):
        if os.path.exists(socket_path):
            os.remove(socket_path)

    def __setup_httpd_thread(self, socket_path):
        """Setup internal HTTPd server that this endpoints relies on to serve
           requests.

        Args:
            path (str): Unix socket path, that internal httpd server will listen
                on
        """
        self._httpd = UnixSocketStatefulHTTPServer(self._context,
                                                   socket_path,
                                                   self._handler_class)

        httpd_thread_name = "UnixSocketHttpdThread-{}".format(self.id)
        self._httpd_thread = threading.Thread(target=self._httpd.serve_forever,
                                              name=httpd_thread_name)

        # nginx spawns worker processes as 'nobody/nogroup', so we need to
        # make the socket available to it.
        os.chmod(socket_path, 0o777)
