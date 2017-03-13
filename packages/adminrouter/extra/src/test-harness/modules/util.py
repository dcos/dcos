# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""This module provides a set of helper functions for tests.

    Attributes:
        LOG_LINE_SEARCH_INTERVAL (decimal): Defines (in seconds), intervals
            between subsequent scans of log buffers.
"""

import code
import logging
import os
import pyroute2
import re
import signal
import time
import traceback


LOG_LINE_SEARCH_INTERVAL = 0.2

log = logging.getLogger(__name__)


class GuardedSubprocess():
    """Context manager for Subproces instances

       The purpose of this class is to provide reliable cleanup for all Subprocess
       class instances (AR & friends), no matter the tests results or errors.

       Using plain pytest fixture instead is difficult - some of the tests
       need to control when exactly i.e. AR is started and stopped. The test-scoped
       AR fixture would just start AR before running the test body and stop it
       right after it finishes.

       @contextlib.contextmanager decorator for some reason does not create
       context managers that work in some of the cases (__exit__ is not called).
       So for this reason we define one directly.
    """
    def __init__(self, subp):
        self._subp = subp

    def __enter__(self):
        self._subp.start()

    def __exit__(self, *_):
        self._subp.stop()


class SearchCriteria:
    """A helper class that is meant to group together search criteria for
       LineBufferFilter objects
    """
    __slots__ = ['occurrences', 'exact']

    def __init__(self, occurrences, exact):
        """Initialize new SearchCriteria object

        Attributes:
            occurrences (int): number of occurrences of the particular regexp
              in the buffer
            exact (bool): should the `occurrences` attribute be treated as
              `exact number of occurrences` (True), or `at least that many
              occurrences`.
        """
        self.occurrences = occurrences
        self.exact = exact


class LineBufferFilter():
    """Helper class for grepping line buffers created by LogCatcher class

    This class is meant to simplify searching of particular strings in line
    buffers created by LogCatcher object for subprocess run by this test
    harness.

    It exposes two interfaces:
    * context manager interface for isolating logs from particular event, i.e.
        lbf = LineBufferFilter(filter_regexp,
                               line_buffer=ar_process.stderr_line_buffer)

        with lbf:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=header)

        assert lbf.extra_matches == {}

        In this case log buffer will be scanned only for entries that were added
        while executing the `requests.get()` call.

    * `.scan_log_buffer()` approach in case string should be searched from the
        beginning of the log.

        lbf = LineBufferFilter(filter_regexp,
                               line_buffer=ar_process.stderr_line_buffer)

        lbf.scan_log_buffer()

        assert lbf.extra_matches == {}

    The result - whether the log was found or not can be determined using
    `extra_matches` property which provides detailed information about the
    lines matched and the number of occurrences.
    """
    _filter_regexpes = None
    _line_buffer = None
    _line_buffer_start = None
    _timeout = None

    def __init__(self, filter_regexpes, line_buffer, timeout=3):
        """Initialize new LineBufferFilter object

        Create new LineBufferFilter object configured to search for string
        `filter_regexp` in line buffer `filter_regexp` for as much as `timeout`
        seconds.

        Args:
            line_buffer (list()): an array of log lines, as presented by `.*_line_buffer()`
              method of the object we want to scan lines for.
            timeout (int): how long before LineBufferFilter gives up on searching for
              filter_regexp in line_buffer
            filter_regexp: see below

        `filter_regexp` argument can have 3 forms:
            * regexp that the instance should look for in the logs. It has to be
              matched at least once.
            * a list of regexpes that the instance should look for in the logs.
              Each one of them has to be matched at least once.
            * a dictionary with regexp as a key and SearchCriteria object as
              the value. The SearchCriteria object determines how exactly given
              regexp is going to be matched
        """
        assert isinstance(timeout, int)
        assert timeout >= LOG_LINE_SEARCH_INTERVAL
        assert isinstance(line_buffer, list)

        self._line_buffer = line_buffer
        self._timeout = timeout

        self._parse_filter_regexpes(filter_regexpes)

    def _parse_filter_regexpes(self, filter_regexpes):
        """Parse filter regexpes into standardized dictionary

        This method implement the polymorphism described in `__init__` method
        of this class. Both single string and list arguments are converted here
        to standardized form of dict({<regexp>: SearchCriteria()}) object.


        Arguments:
            filter_regexpes: see description of this argument in `__init__`
            method
        """
        if isinstance(filter_regexpes, str):
            self._filter_regexpes = {filter_regexpes: SearchCriteria(1, False)}
        elif isinstance(filter_regexpes, list):
            self._filter_regexpes = {x: SearchCriteria(1, False) for x in filter_regexpes}
        elif isinstance(filter_regexpes, dict):
            self._filter_regexpes = filter_regexpes
        else:
            assert False, "Unsupported filter strings object!"

    def __enter__(self):
        assert self._line_buffer_start is None
        assert self._line_buffer is not None

        self._line_buffer_start = len(self._line_buffer)

    def scan_log_buffer(self):
        """Scan for `filter_regexp` since the beginning of the given instance's log

        This is a convenience function that forces search of the `filter_regexp`
        since the beginning of the log buffer. It's does by simply fixing the
        start position and calling the __exit__() method of the context manager
        """
        # Bit hacky, but good enough™
        self._line_buffer_start = 0
        self.__exit__()

    def _match_line_against_filter_regexpes(self, line):
        """Helper method that abstracts matching of the line against multiple
           regexpes.

        Each match is registered, so that it's possible to determine if
        search criteria were met.

        Arguments:
            line (str): a line to match
        """
        for filter_regexp in self._filter_regexpes:
            if re.search(filter_regexp, line, flags=0):
                sc = self._filter_regexpes[filter_regexp]
                if sc.exact and sc.occurrences <= 0:
                    log.warning("filter string `%s` matched more times than requested",
                                filter_regexp)
                sc.occurrences -= 1

    def __exit__(self, *unused):
        """Context manager __exit__ method for filter string search

        This is the heart of the LineBufferFilter - the whole matching happens
        here.
        """
        msg_fmt = "Beginning to scan for line `%s` in logline buffer"
        log.debug(msg_fmt, list(self._filter_regexpes.keys()))

        deadline = time.time() + self._timeout

        while time.time() < deadline:
            lines_scanned = 0

            for log_line in self._line_buffer[self._line_buffer_start:]:
                self._match_line_against_filter_regexpes(log_line)
                if self._all_found:
                    return
                lines_scanned += 1

            self._line_buffer_start = self._line_buffer_start + lines_scanned

            msg_fmt = "waiting for strings `%s` to appear in logline buffer"
            log.debug(msg_fmt, self._regexpes_still_not_matched)

            time.sleep(LOG_LINE_SEARCH_INTERVAL)

        msg_fmt = "Timed out while waiting for strings `%s` to appear in logline buffer"
        log.debug(msg_fmt, self._regexpes_still_not_matched)

    @property
    def _regexpes_still_not_matched(self):
        """Helper function that returns a list of regexpes that still has not
        met search criterias"""
        return [x for x in self._filter_regexpes if self._filter_regexpes[x].occurrences > 0]

    @property
    def _all_found(self):
        """Helper - check if all search criterias have been met ?
        """
        return all([sc.occurrences <= 0 for sc in self._filter_regexpes.values()])

    @property
    def extra_matches(self):
        """Detailed information about regexpes that has and/or has not been
        matched.

        This property can be useful if i.e. there were mixed search criterias -
        some of the regexpes had to be strictly matched, some not.

        Return:
            It returns a dictionary with regexpes from `filter_regexpes` argument
        of `__init__()` as keys and the number of matches as values. This number
        can have 3 different values:
            * if the regexp was matched exactly the number of times specified
        (once for regexp and list of regexpes `filter_regexpes` argument), it has
        a value of zero and the key is not present in the resulting dictionary
            * if the input has not been matched at all in case of regexp and list
        of regexpes `filter_regexpes` argument, or less than requested number
        of times in case of detailed `filter_regexpes` form, it's a positive
        number
            * if the input has been matched more times than anticipated - a
        negative number.

        Usually it's used in `assert lbf.extra_matches == {}` form in tests
        """
        left = {}
        for filter_regexp in self._filter_regexpes:
            search_criteria = self._filter_regexpes[filter_regexp]
            if search_criteria.occurrences > 0 or \
                    search_criteria.exact and search_criteria.occurrences < 0:
                search_criteria.occurrences = -search_criteria.occurrences
                left[filter_regexp] = search_criteria.occurrences

        return left


def configure_logger(pytest_config):
    """ Set up a logging basing on pytest cmd line args.

    Configure log verbosity basing on the --log-level command line
    argument (INFO by default).
    """

    tests_log_level = pytest_config.getoption('tests_log_level')
    rootlogger = logging.getLogger()

    # Set up a stderr handler for the root logger, and specify the format.
    fmt = "%(asctime)s.%(msecs)03d %(name)s:%(lineno)s %(levelname)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt="%y%m%d-%H:%M:%S"
        )

    if tests_log_level != 'disabled':
        level = getattr(logging, tests_log_level.upper())
        rootlogger.setLevel(level)
    else:
        rootlogger.handlers = []
        rootlogger.addHandler(logging.NullHandler())


def add_lo_ipaddr(ip_addr, prefix_len):
    """Add an ipv4 address to loopback interface.

    Add an ipv4 address to loopback provided that it does not already exist.

    Args:
        ip_addr (str): IP address
        prefix_len (int): prefix length
    """
    iproute2 = pyroute2.IPRoute()
    idx = iproute2.link_lookup(ifname='lo')[0]

    existing_ips = iproute2.get_addr(index=idx)
    for existing_ip in existing_ips:
        if existing_ip['family'] != 2:
            # Only support only ipv4 for now, so this one is not ours
            continue

        if existing_ip['prefixlen'] != prefix_len:
            # Not ours, but yes - same IP with different prefix will bork
            # things up. But this should not happen during normal OP.
            continue

        for attr in existing_ip['attrs']:
            if attr[0] == "IFA_ADDRESS" and attr[1] == ip_addr:
                msg_fmt = "Not adding addres `%s/%s`` as it already exists`"
                log.info(msg_fmt, ip_addr, prefix_len)
                return

    iproute2.addr('add', index=idx, address=ip_addr, mask=prefix_len)


def del_lo_ipaddr(ip_addr, prefix_len):
    """Remove ipv4 address from loopback interface

    Remove existing ipv4 address, defined by ip_addr and prefix_len, from
    loopback interface.

    Args:
        ip_addr (str): IP address
        prefix_len (int): prefix length

    Raises:
        NetlinkError: failed to remove address, check exception data for details.
    """
    iproute2 = pyroute2.IPRoute()
    idx = iproute2.link_lookup(ifname='lo')[0]
    iproute2.addr('del', index=idx, address=ip_addr, mask=prefix_len)


def setup_thread_debugger():
    """Setup a thread debbuger for pytest session

    This function, based on http://stackoverflow.com/a/133384, is meant to
    add debugging facility to pytest that will allow to debug deadlock that
    may sometimes occur.
    """
    def debug(signal, frame):
        """Interrupt running process and provide a python prompt for
        interactive debugging."""
        d = {'_frame': frame}  # Allow access to frame object.
        d.update(frame.f_globals)  # Unless shadowed by global
        d.update(frame.f_locals)

        i = code.InteractiveConsole(d)
        message = "Signal received : entering python shell.\nTraceback:\n"
        message += ''.join(traceback.format_stack(frame))
        i.interact(message)

    signal.signal(signal.SIGUSR1, debug)  # Register handler


def ar_listen_link_setup(role, is_ee):
    assert role in ['master', 'agent']

    if is_ee:
        flavour = 'ee'
    else:
        flavour = 'open'

    src_path = "/opt/mesosphere/etc/adminrouter-listen-{}.conf".format(flavour)
    dst_path = "adminrouter-listen-{}.conf".format(role)

    if os.path.exists(src_path):
        assert os.path.islink(src_path)

        cur_dst_path = os.readlink(src_path)

        if cur_dst_path != dst_path:
            os.unlink(src_path)
            os.symlink(dst_path, src_path)

        return

    os.symlink(dst_path, src_path)
