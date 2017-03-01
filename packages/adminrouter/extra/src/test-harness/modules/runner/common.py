# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""
Common code for AR instance management.
"""

import abc
import logging
import os
import pytest
import select
import signal
import socket
import subprocess
import threading
import time

from exceptions import LogSourceEmpty
from util import LOG_LINE_SEARCH_INTERVAL

log = logging.getLogger(__name__)

# These reflect AR's cache production settings (in seconds):
CACHE_FIRST_POLL_DELAY = 2
CACHE_POLL_PERIOD = 25
CACHE_EXPIRATION = 20
CACHE_MAX_AGE_SOFT_LIMIT = 35
CACHE_MAX_AGE_HARD_LIMIT = 259200  # 3 days * 24h * 60 minutes * 60 seconds
CACHE_BACKEND_REQUEST_TIMEOUT = 10
CACHE_REFRESH_LOCK_TIMEOUT = 20


class SyslogMock():
    """A mock of system syslog

    A simple mock of system's syslog, that listens of UDP Unix socket and pushes
    all messages to the log catcher instance.

    Log messages are not formatted nor decoded in any way, thus they are
    prefixed with syslog-protocol artifacts. This may be addressed at some
    point though

    Attributes:
        SOCKET_PATH (str): path where the unix socket should be created
    """
    SOCKET_PATH = "/dev/log"
    _log_catcher = None

    def _cleanup_stale_sockets(self):
        try:
            os.unlink(self.SOCKET_PATH)
        except OSError:
            if os.path.exists(self.SOCKET_PATH):
                raise

    def _bind_socket(self):
        """Bind to the socket specified by self.SOCKET_PATH

        Worth noting is that Nginx setuids to user nobody, thus it is
        necessary to give very open permission for the socket so that
        it can be accessed by the AR instance
        """
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._socket.bind(self.SOCKET_PATH)
        os.chmod(self.SOCKET_PATH, 0o666)

    def __init__(self, log_catcher):
        """Initialize new SyslogMock instance

        Args:
            log_catcher (object: LogCatcher()): a LogCatcher instance that is
                going to be used by the mock to store captured messages.
        """
        self._log_catcher = log_catcher

        self._cleanup_stale_sockets()
        self._bind_socket()

        self._log_catcher.add_fd(self._socket, log_file='syslog.stdout.log')

    def stop(self):
        """Stop the syslog mock and perform the cleanup"""
        self._socket.close()
        os.remove(self.SOCKET_PATH)

    @property
    def stdout_line_buffer(self):
        """Interface for accessing log lines captured by syslog mock

        Returns:
            This returns a reference to the list that log catcher internally
            uses to append log lines to. Thus it is *VERY* important to not to
            modify this list and treat it as Read-Only
        """
        return self._log_catcher.line_buffer(self._socket)


class LogWriter():
    """LogWriter handles log lines gathered by LogCatcher.

    It takes care of storing them internally in a list(), writing them to
    a log file if requested, and logging the log lines to python logger

    Worth noting is that this class should be embedded by LogCatcher object.

    Attributes:
        MAX_LINE_LENGTH (int): maximum length of the line that is supported
            by all LogWriter instances.
    """
    MAX_LINE_LENGTH = 8192

    _fd = None
    _log_level = None
    _log_fd = None
    _line_buffer = None

    @staticmethod
    def _normalize_line_bytes(line_bytes):
        """Normalize newlines in given bytes array

        Args:
            line_byes (b''): bytes array that should be normalized

        Returns:
            Normalized bytes array.
        """
        if len(line_bytes) >= 2 and line_bytes.endswith(b'\r\n'):
            return line_bytes[:-2]

        if len(line_bytes) and line_bytes.endswith(b'\n'):
            return line_bytes[:-1]

        return line_bytes

    def _read_line_from_fd(self):
        """Read a line from stored file descriptor

        Depending on the socket type, either datagram or file interface is
        used.

        Returns:
            A bytes array representing read bytes.
        """
        if isinstance(self._fd, socket.socket):
            assert self._fd.type == socket.SOCK_DGRAM

            # Each datagram is a separate log line
            line_bytes = self._fd.recv(self.MAX_LINE_LENGTH)

        else:
            # Read only one line at a time, so that we do not starve
            # other pipes/sockets
            line_bytes = self._fd.readline()

        line_bytes = self._normalize_line_bytes(line_bytes)

        return line_bytes

    def _raise_if_source_is_empty(self, event_type):
        """Helper method used for determining if given log fd is empty or not"""

        if isinstance(self._fd, socket.socket):
            if event_type == select.POLLNVAL:
                raise LogSourceEmpty()
        else:
            if event_type == select.POLLHUP:
                raise LogSourceEmpty()

    def __init__(self, fd, log_file, log_level=None):
        """Initialize new LogWriter instance

        Args:
            fd (obj: python file descriptor): file descriptor from which log
                lines should be read.
            log_file (str): log all the gathered log lines to file at the
                given location
            log_level (int): log level with which all the log lines should be
                logged with, do not log to stdout if None
        """
        self._fd = fd
        self._log_level = log_level
        self._line_buffer = list()
        self._log_fd = open(log_file, 'ab', buffering=0)

    def stop(self):
        """Stop LogWriter instance and perform a cleanup

        This method:
          * delimits end of LogWriter instance logging in the log file with help
            of `scissors` utf8 character, so that it is easier to separate output
            from subsequent instances of given object (i.e. nginx) in the same
            log file.
          * closes fog file file descriptor
        """
        delimiter = u"\u2704".encode('utf-8')
        msg = delimiter * 10 + b" Logging of this instance ends here " + delimiter * 10
        self._append_line_to_log_file(msg)
        self._log_fd.close()

    def write(self, event_type):
        """Method used by LogCatcher instance for sending the data to
        LogWriter for storing

        Args:
            event_type (int): event type as described by pool() objects interface
                (https://docs.python.org/3/library/select.html#poll-objects)
        """
        self._raise_if_source_is_empty(event_type)

        line_bytes = self._read_line_from_fd()
        if self._log_fd is not None:
            self._append_line_to_log_file(line_bytes)

        # yeah, we are guessing encoding here:
        line = line_bytes.decode('utf-8', errors='backslashreplace')
        if self._log_level is not None:
            log.log(self._log_level, line)
        self._append_line_to_line_buffer(line)

    def _append_line_to_line_buffer(self, line):
        self._line_buffer.append(line)

    def _append_line_to_log_file(self, line):
        normalized_line = line + b'\n'
        self._log_fd.write(normalized_line)

    @property
    def line_buffer(self):
        """Expose internal log line buffer

        This method exposes internal log buffer to the caller.

        Returns:
            A list with each log line as a single element.
        """
        return self._line_buffer


class LogCatcher():
    """A central log-gathering facility.

    This object collects all the logs that come from subprocesses (like i.e.
    nginx, dnsmasq, etc...) and syslog mock. It makes them available as an
    easy to use lists that can be grepped/searched/monitored. Internally, it
    uses LogWriter instances for storing the data.

    Worth noting is that this class should be embedded by other objects - most
    notably objects derived from ManagedSubrocess abstract class.
    """
    _POLL_TIMEOUT = 0.5
    _LOG_DIR = './test-harness/logs/'
    _GIT_KEEP_FILE = '.keep'

    _termination_flag = None
    _poll = None
    _writers = None

    def _monitor_process_outputs(self):
        """A main loop where event are demultiplexed

        The purpose of this function is to monitor all registered file
        descriptors and in case when new data is available - hand of
        taking care of it to LogWriter instance that is responsible
        for given file descriptor.

        poll() call generally seems to be easier to use and better fits
        our use case than e.g. plain select() (no need for global lock
        while updating FD lists):
        * http://stackoverflow.com/a/25249958
        * http://www.greenend.org.uk/rjk/tech/poll.html
        """
        while True:
            ready_to_read = self._poll.poll(self._POLL_TIMEOUT)

            if not len(ready_to_read) and self._termination_flag.is_set():
                # Nothing else to read, termination requested
                return

            for fd_tuple in ready_to_read:
                fd_no, event = fd_tuple
                writer = self._writers[fd_no]

                try:
                    writer.write(event)
                except LogSourceEmpty:
                    self._poll.unregister(fd_no)
                    writer.stop()
                    log.info("LogCatcher unregistered fd `%s`", fd_tuple[0])

    def _cleanup_log_dir(self):
        """Remove all the old log file from the log directory

        Removes all the old log files from the log directory before logging
        anything new. This is necessary because we are always appending to the
        logfiles due to multiple instances being created and destroy during
        the tests, and appending to old log files could confuse tests developers.
        """
        for f_name in os.listdir(self._LOG_DIR):
            if f_name == self._GIT_KEEP_FILE:
                log.debug("Skipping git keep-file: `%s`", f_name)
                continue

            f_path = os.path.join(self._LOG_DIR, f_name)

            if os.path.isfile(f_path):
                log.debug("Removing old log `%s`", f_path)
                os.unlink(f_path)

        log.info("Logging path `%s` has been cleaned up", self._LOG_DIR)

    def __init__(self):
        """Initialize new LogCatcher object"""
        self._termination_flag = threading.Event()
        self._poll = select.poll()
        self._writers = {}

        self._cleanup_log_dir()

        self._logger_thread = threading.Thread(
            target=self._monitor_process_outputs, name='LogCatcher')
        self._logger_thread.start()
        log.info("LogCatcher thread has started")

    def add_fd(self, fd, log_file, log_level=None):
        """Begin handling new file descriptor

        This method adds given file descriptor to the set monitored by
        internal poll() call and creates new LogWriter instance for it.

        Args:
            fd (obj: python file descriptor): file descriptor from which log
                lines should be read.
            log_file (str): if not None - log all the gathered log lines to
                file at the given location
            log_level (int): log level with which all the log lines should be
                logged with, do not log to stdout if None
        """
        assert fd.fileno() not in self._writers

        if log_file is not None:
            log_path = os.path.join(self._LOG_DIR, log_file)
        else:
            log_path = None

        writer = LogWriter(fd, log_path, log_level)

        self._writers[fd.fileno()] = writer

        self._poll.register(fd, select.POLLIN | select.POLLHUP)
        log.info("LogCatcher registered fd `%d`", fd.fileno())

    def stop(self):
        """Stop the LogCatcher instance and perform resource cleanup."""
        self._termination_flag.set()

        while self._logger_thread.is_alive():
            self._logger_thread.join(timeout=0.5)
            log.info("Waiting for LogCatcher thread to exit")

        log.info("LogCatcher thread has terminated, bye!")

    def line_buffer(self, fd):
        """Expose line buffer used for logging data from given file descriptor

        Args:
            fd (obj: python file descriptor): file descriptor for which log
                line buffer should be returned

        Returns:
            A list that use used by LogWriter responsible for handling given
            file descriptor to store log lines.
        """
        return self._writers[fd.fileno()].line_buffer


class ManagedSubprocess(abc.ABC):
    """Abstract base class that represents all behaviour shared by subprocesses
       manged by pytest run.

       It allows for defining of both command line arguments and environment
       variables that will be passed to subprocess. By default the environment
       variables are all wiped.
    """
    _START_TIMEOUT = 3
    _EXIT_TIMEOUT = 5
    _INIT_COMPLETE_STR = None

    _args = None
    _env = None
    _log_catcher = None
    _process = None

    binary = None
    config_path = None

    def __init__(self, log_catcher):
        """Initialize new subprocess instance.

        Args:
            log_catcher (obj: LogCatcher): a log catcher instance that will
                be handling logs/output created by this subprocess.
        """
        self._env = {}
        self._args = []
        self._log_catcher = log_catcher

    @property
    def id(self):
        """Identify this subprocess instance

        Return a string that will be identifying this ManagedSubprocess object
        instance.

        Plain class name should be good enough for now, we may extend it
        later on.
        """
        return self.__class__.__name__

    @property
    def stdout(self):
        """Return stdout file descriptor of this process"""
        assert_msg = "`{}` process must be initialized first".format(self.id)
        assert self._process is not None, assert_msg

        return self._process.stdout

    @property
    def stderr(self):
        """Return stderr file descriptor of this process"""
        assert_msg = "`{}` process must be initialized first".format(self.id)
        assert self._process is not None, assert_msg

        return self._process.stderr

    def start(self):
        """Start a subprocess

        This method makes python actually spawn the subprocess and wait for it
        to finish initializing.
        """
        self._start_subprocess()

        self._register_stdout_stderr_to_logcatcher()

        if not self._wait_for_subprocess_to_finish_init():
            self.stop()
            pytest.exit("Failed to start `{}` process".format(self.id))

    def _start_subprocess(self):
        msg_fmt = "Starting `%s`, env: `%s`"
        log.debug(msg_fmt, ' '.join(self._args), self._env)
        self._process = subprocess.Popen(self._args,
                                         env=self._env,
                                         stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE,
                                         bufsize=0,
                                         shell=False,
                                         universal_newlines=False,
                                         start_new_session=True,
                                         )

    def stop(self):
        """Stop ManagedSubprocess instance and perform a cleanup

        This method makes sure that there are no child processes left after
        the object destruction finalizes. In case when a process cannot stop
        on it's own, it's forced to using SIGTERM/SIGKILL.
        """
        self._process.poll()
        if self._process.returncode is not None:
            msg_fmt = "`%s` process has already terminated with code `%s`"
            pytest.exit(msg_fmt % (self.id, self._process.returncode))
            return

        log.info("Send SIGINT to `%s` master process", self.id)
        self._process.send_signal(signal.SIGINT)
        try:
            self._process.wait(self._EXIT_TIMEOUT / 2.0)
        except subprocess.TimeoutExpired:
            log.info("Send SIGTERM to `%s` master process", self.id)
            self._process.send_signal(signal.SIGTERM)
            try:
                self._process.wait(self._EXIT_TIMEOUT / 2.0)
            except subprocess.TimeoutExpired:
                log.info("Send SIGKILL to all `%s` processess", self.id)
                os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                log.info("wait() for `%s` master process to die", self.id)
                self._process.wait()

        log.info("`%s` master process has terminated", self.id)

    def _wait_for_subprocess_to_finish_init(self):
        """Monitor process out for indication that the init process is complete

        Using internal LogCatcher instance, monitor process output is search of
        self._INIT_COMPLETE_STR in one of log lines. If found, it is assumed
        that the process has finished init.
        """
        if self._INIT_COMPLETE_STR is None:
            msg_fmt = ("Not waiting for process `%s` to start and assuming that"
                       " it is already up")
            log.warn(msg_fmt, self.id)
            return True

        deadline = time.time() + self._START_TIMEOUT
        log_buf_pos = 0
        log_buf = self._init_log_buf

        while time.time() < deadline:
            self._process.poll()
            if self._process.returncode is not None:
                msg_fmt = "`%s` process exited prematurely during init"
                log.warning(msg_fmt, self.id)
                return False

            log_buf_end = len(log_buf) - 1
            if log_buf_end >= log_buf_pos:
                for line in log_buf[log_buf_pos:]:
                    if self._INIT_COMPLETE_STR in line:
                        log.info("`%s` init process complete", self.id)
                        return True
                log_buf_pos = log_buf_end

            log.debug("Waiting for `%s` to start...", self.id)
            time.sleep(LOG_LINE_SEARCH_INTERVAL)

        msg_fmt = "`%s` failed to start in `%d` seconds"
        log.warning(msg_fmt, self.id, self._START_TIMEOUT)
        return False

    @abc.abstractmethod
    def _init_log_buf(self):
        """This is just a helper method that inheriting classes override, in
        order to indicate which log buffer should be monitored for
        self._INIT_COMPLETE_STR
        """
        pass

    @property
    def stdout_line_buffer(self):
        """Return line buffer where all stdout output of this ManagedSubprocess
        object resides"""
        return self._log_catcher.line_buffer(self.stdout)

    @property
    def stderr_line_buffer(self):
        """Return line buffer where all stderr output of this ManagedSubprocess
        object resides"""
        return self._log_catcher.line_buffer(self.stderr)

    @abc.abstractmethod
    def _register_stdout_stderr_to_logcatcher(self):
        """This is just a helper method that inheriting classes override, in
        order to perform customized registration of log outputs/file descriptors
        to internal LogCatcher instance.
        """
        pass


class DNSMock(ManagedSubprocess):
    """A DNS server subprocess that mocks DNS facilites in DC/OS

    This class is used to spawn DNS servers based on dnsmasq, that will server
    static content basing on /etc/hosts.dnsmasq file contents and will forward
    all the requests that cannot be satisfied using it to upstream google
    servers (8.8.8.8/8.8.4.4)

    The complexity of DNS protocol makes it infeasible to implement it in pure
    python. Thus the decision was made to just launch new child process that will
    be answering all the requests stemming from Nginx that is being tested.

    Due to the fact that depending on the type of AR in testing (master/agent),
    different ports are used, dnsmasq can be started on different port depending
    on init parameters.
    """

    _INIT_COMPLETE_STR = "read /etc/hosts.dnsmasq"

    def _register_stdout_stderr_to_logcatcher(self):
        """Please check ManagedSubprocess'es class method description"""
        log_filename = 'dns.port_{}.stdout.log'.format(self._port)
        self._log_catcher.add_fd(self.stdout, log_file=log_filename)

        log_filename = 'dns.port_{}.stderr.log'.format(self._port)
        self._log_catcher.add_fd(self.stderr, log_file=log_filename)

    def __init__(self, log_catcher, port=53):
        """Initialize new DNSMock object

        Args:
            port (int): port on which instance should listen for new requests
            log_catcher (object: LogCatcher()): a LogCatcher instance that is
                going to be used by the mock to store captured messages.
        """
        super().__init__(log_catcher)
        self._port = port

        self._args = ["/usr/sbin/dnsmasq",
                      '--no-daemon',
                      '--log-queries',
                      '--port={}'.format(port),
                      '--log-async=15',
                      '--conf-file=/etc/dnsmasq.conf']

    @property
    def _init_log_buf(self):
        """Please check ManagedSubprocess'es class method description"""
        return self.stderr_line_buffer


class NginxBase(ManagedSubprocess):
    """This class represents AR behaviour shared between both EE and Open.

    It should not be instantiated directly but instead inheriting classes should
    override/extend its methods.
    """
    _INIT_COMPLETE_STR = 'start worker processes'

    def _register_stdout_stderr_to_logcatcher(self):
        """Please check ManagedSubprocess'es class method description"""
        self._log_catcher.add_fd(self.stdout, log_file='nginx.stdout.log')
        self._log_catcher.add_fd(self.stderr, log_file='nginx.stderr.log')

    @property
    def _init_log_buf(self):
        """Please check ManagedSubprocess'es class method description"""
        return self.stderr_line_buffer

    def _set_ar_env_from_val(self, env_name, env_val):
        """Set environment variable for this AR instance

        Args:
            env_name: name of the environment variable to set
            env_val: value that the new environment should have, if None - it
                will be skipped/not set.
        """
        if env_val is None:
            log.info("Not setting env var `%s` as it's None", env_name)
            return

        self._env[env_name] = env_val

    def _set_ar_env_from_environment(self, env_name):
        """Set environment variable for this AR instance basing on existing
           environment variable.

           This function is esp. useful in cases when certain env. variable
           should be copied from existing env vars that pytest runtimes sees.

        Args:
            env_name: name of the environment variable to set
        """
        env_val = os.environ.get(env_name)
        if env_val is None:
            msg_fmt = "`%s` env var is not set, cannot pass it to subprocess"
            log.warning(msg_fmt, env_name)
            return

        self._env[env_name] = env_val

    def _set_ar_cmdline(self):
        """Helper function used to determine Nginx command line variables
           basing on how the instance was configured
        """
        openresty_dir = os.environ.get('AR_BIN_DIR')
        assert openresty_dir is not None, "'AR_BIN_DIR' env var is not set!"
        self.binary = os.path.join(openresty_dir, "nginx", "sbin", "nginx")

        config_file_name = "nginx.{}.conf".format(self._role)
        self.config_path = os.path.join(openresty_dir,
                                        "nginx",
                                        "conf",
                                        config_file_name)

        self._args = [self.binary,
                      '-c', self.config_path,
                      '-g', 'daemon off;',
                      ]

    def _set_ar_env(self,
                    auth_enabled,
                    default_scheme,
                    upstream_mesos,
                    upstream_marathon,
                    cache_first_poll_delay,
                    cache_poll_period,
                    cache_expiration,
                    cache_max_age_soft_limit,
                    cache_max_age_hard_limit,
                    cache_backend_request_timeout,
                    cache_refresh_lock_timeout,
                    ):
        """Helper function used to determine Nginx env. variables
           basing on how the instance was configured
        """
        self._set_ar_env_from_val('ADMINROUTER_ACTIVATE_AUTH_MODULE',
                                  str(auth_enabled).lower())
        self._set_ar_env_from_val('DEFAULT_SCHEME', default_scheme)
        self._set_ar_env_from_val('UPSTREAM_MESOS', upstream_mesos)
        self._set_ar_env_from_val('UPSTREAM_MARATHON', upstream_marathon)
        self._set_ar_env_from_val('CACHE_FIRST_POLL_DELAY', str(cache_first_poll_delay))
        self._set_ar_env_from_val('CACHE_POLL_PERIOD', str(cache_poll_period))
        self._set_ar_env_from_val('CACHE_EXPIRATION', str(cache_expiration))
        self._set_ar_env_from_val('CACHE_MAX_AGE_SOFT_LIMIT',
                                  str(cache_max_age_soft_limit))
        self._set_ar_env_from_val('CACHE_MAX_AGE_HARD_LIMIT',
                                  str(cache_max_age_hard_limit))
        self._set_ar_env_from_val('CACHE_BACKEND_REQUEST_TIMEOUT',
                                  str(cache_backend_request_timeout))
        self._set_ar_env_from_val('CACHE_REFRESH_LOCK_TIMEOUT',
                                  str(cache_refresh_lock_timeout))
        self._set_ar_env_from_environment('AUTH_ERROR_PAGE_DIR_PATH')

    def __init__(self,
                 auth_enabled=True,
                 default_scheme="http://",
                 upstream_mesos="http://127.0.0.2:5050",
                 upstream_marathon="http://127.0.0.1:8080",
                 role="master",
                 log_catcher=None,
                 cache_first_poll_delay=CACHE_FIRST_POLL_DELAY,
                 cache_poll_period=CACHE_POLL_PERIOD,
                 cache_expiration=CACHE_EXPIRATION,
                 cache_max_age_soft_limit=CACHE_MAX_AGE_SOFT_LIMIT,
                 cache_max_age_hard_limit=CACHE_MAX_AGE_HARD_LIMIT,
                 cache_backend_request_timeout=CACHE_BACKEND_REQUEST_TIMEOUT,
                 cache_refresh_lock_timeout=CACHE_REFRESH_LOCK_TIMEOUT,
                 ):
        """Initialize new Nginx instance

        Args:
            role ('master'|'agent'): the role of this Nginx instance - either
                AR master or AR agent.
            log_catcher (object: LogCatcher()): a LogCatcher instance that is
                going to be used by the mock to store captured messages.
            auth_enabled (bool): translates to `ADMINROUTER_ACTIVATE_AUTH_MODULE`
                env var
            default_scheme (str),
            upstream_mesos (str),
            upstream_marathon (str),
            cache_first_poll_delay (int),
            cache_poll_period (int),
            cache_backend_request_timeout (int),
            CACHE_REFRESH_LOCK_TIMEOUT (int),
            cache_expiration (int),
            cache_max_age_soft_limit (int),
            cache_max_age_hard_limit (int): translate to
                `DEFAULT_SCHEME`,
                `UPSTREAM_MESOS`,
                `UPSTREAM_MARATHON`
                `CACHE_FIRST_POLL_DELAY`,
                `CACHE_POLL_PERIOD`,
                `CACHE_EXPIRATION`,
                `CACHE_BACKEND_REQUEST_TIMEOUT`,
                `CACHE_REFRESH_LOCK_TIMEOUT`,
                `CACHE_MAX_AGE_SOFT_LIMIT`,
                `CACHE_MAX_AGE_HARD_LIMIT` env vars. Please check the documentation
                and/or the source code and its comments for details.

        """
        assert role in ("master", "agent"), "wrong value of 'role' param"
        self._role = role

        super().__init__(log_catcher)

        self._set_ar_env(auth_enabled,
                         default_scheme,
                         upstream_mesos,
                         upstream_marathon,
                         cache_first_poll_delay,
                         cache_poll_period,
                         cache_expiration,
                         cache_max_age_soft_limit,
                         cache_max_age_hard_limit,
                         cache_backend_request_timeout,
                         cache_refresh_lock_timeout,
                         )
        self._set_ar_cmdline()

    def make_url_from_path(self, path='/exhibitor/some/path'):
        """A helper function used in tests that is meant to abstract AR
           listen port and provide single point of change for updating
           the place where all the test expect AR to listen for requests."""
        if self._role == 'master':
            base = 'http://127.0.0.1:80/'
        else:
            base = 'http://127.0.0.1:61001/'

        if not len(path):
            return base + '/'

        if path[0] != '/':
            return base + path

        return base + path[1:]


class Vegeta(ManagedSubprocess):
    # Wait longer, give Vegeta more time to save report before SIGKILLing it
    _EXIT_TIMEOUT = 15

    # Disable waiting for confirmation that Vegeta started - it starts
    # benchmark imediatelly without any stdout/stderr message
    _INIT_COMPLETE_STR = None

    _TARGETS_FILE = "/tmp/vegeta-targets.txt"
    _REPORT_FILE = "/tmp/vegeta-report.bin"
    _VEGETA_BIN = "/usr/local/bin/vegeta"

    _results = None

    def _register_stdout_stderr_to_logcatcher(self):
        """Please check ManagedSubprocess'es class method description"""
        log_filename = 'vegeta.stdout.log'
        self._log_catcher.add_fd(self.stdout, log_file=log_filename)

        log_filename = 'vegeta.stderr.log'
        self._log_catcher.add_fd(self.stderr, log_file=log_filename)

    def _cleanup_old_report_file(self):
        try:
            os.unlink(self._REPORT_FILE)
        except OSError:
            if os.path.exists(self._REPORT_FILE):
                raise

    def _setup_targets_file(self, target, jwt=None):
        body = "GET {}\n".format(target)
        if jwt is not None:
            body += "Authorization: {}\n".format(jwt['Authorization'])

        with open(self._TARGETS_FILE, 'w') as fh:
            fh.write(body)

    def __init__(self, log_catcher, target, jwt=None, rate=3):
        """Initialize new Vegeta object

        Only GET for now.

        Args:
            log_catcher (object: LogCatcher()): a LogCatcher instance that is
                going to be used by the mock to store captured messages.
        """
        super().__init__(log_catcher)

        self._cleanup_old_report_file()
        self._setup_targets_file(target, jwt)

        self._args = [self._VEGETA_BIN,
                      "attack",  # !
                      "-output", self._REPORT_FILE,
                      "-targets", self._TARGETS_FILE,
                      "-rate", str(rate),
                      "-duration", "0",
                      ]

    @property
    def _init_log_buf(self):
        """Please check ManagedSubprocess'es class method description"""
        return self.stdout_line_buffer

    # Report handling was removed, it needs some more work. Please check commit
    # history for details.
