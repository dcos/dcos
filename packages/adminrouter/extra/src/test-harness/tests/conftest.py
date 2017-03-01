# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""This module provides fixtures that are shared among all repository
   flavours (Open/EE)"""

import os
import pytest

from runner.common import (
    DNSMock,
    LogCatcher,
    SyslogMock,
    )
from mocker.jwt import generate_rs256_jwt, generate_hs256_jwt
from util import add_lo_ipaddr, del_lo_ipaddr, ar_listen_link_setup


@pytest.fixture()
def tmp_file(tmpdir):
    """Provide a temporary file in pytest-defined tmp dir

    Returns:
        A path to the tmp file
    """
    return tmpdir.join('tmp_data.json').strpath


@pytest.fixture(scope='session')
def repo_is_ee():
    """Determine the flavour of the repository

    Return:
        True if repository is EE
    """
    cur_dir = os.path.dirname(__file__)
    ee_tests_dir = os.path.abspath(os.path.join(cur_dir, "ee"))
    open_tests_dir = os.path.abspath(os.path.join(cur_dir, "open"))

    is_ee = os.path.isdir(ee_tests_dir) and not os.path.isdir(open_tests_dir)
    is_open = os.path.isdir(open_tests_dir) and not os.path.isdir(ee_tests_dir)

    assert is_ee or is_open, "Unable to determine the variant of the repo"

    return is_ee


@pytest.fixture(scope='session')
def mocker_s(repo_is_ee, syslog_mock, extra_lo_ips):
    """Provide a gc-ed mocker instance suitable for the repository flavour"""
    if repo_is_ee:
        from mocker.ee import Mocker
    else:
        from mocker.open import Mocker

    m = Mocker()
    m.start()

    yield m

    m.stop()


@pytest.fixture(scope='function')
def mocker(mocker_s):
    """An extension to `mocker_s` fixture that adds resetting the mock to
    initial state after each test.

    The division stems from the fact that mocker instance should be created
    only once per session, while it must be reset after every test to it's
    initial state
    """
    yield mocker_s

    mocker_s.reset()


@pytest.fixture(scope='session')
def log_catcher():
    """Provide a session-scoped LogCatcher instance for use by other objects"""
    lc = LogCatcher()

    yield lc

    lc.stop()


@pytest.fixture(scope='session')
def syslog_mock(log_catcher):
    """Provide a session-scoped SyslogMock instance for use by other objects"""
    m = SyslogMock(log_catcher)

    yield m

    m.stop()


@pytest.fixture(scope='session')
def dns_mock(log_catcher, navstar_ips, resolvconf_fixup):
    """Set-up DNS mocks, both for agent AR (port 53) and master AR (port 61053)"""
    m_61053 = DNSMock(log_catcher, port=61053)
    m_61053.start()

    m_53 = DNSMock(log_catcher, port=53)
    m_53.start()

    yield (m_53, m_61053)

    m_61053.stop()
    m_53.stop()


@pytest.fixture(scope='session')
def navstar_ips():
    """Setup IPs that help dns_mock mimic navstar"""
    ips = ['198.51.100.1', '198.51.100.2', '198.51.100.3']

    for ip in ips:
        add_lo_ipaddr(ip, 32)

    yield

    for ip in ips:
        del_lo_ipaddr(ip, 32)


@pytest.fixture(scope='session')
def extra_lo_ips():
    """Setup IPs that are used for simulating e.g. agent, mesos leader, etc.. """
    ips = ['127.0.0.2', '127.0.0.3']

    for ip in ips:
        add_lo_ipaddr(ip, 32)

    yield

    for ip in ips:
        del_lo_ipaddr(ip, 32)


@pytest.fixture(scope='session')
def resolvconf_fixup():
    """Redirect all DNS request to local DNS mock

    Docker's (1.12 ATM) functionality is quite limited when it comes to
    /etc/resolv.conf manipulation: https://github.com/docker/docker/issues/1297

    So the idea is to temporary change the resolv.conf contents during the
    pytest run.
    """

    with open("/etc/resolv.conf", 'rb') as fh:
        old = fh.read()

    with open("/etc/resolv.conf", 'w') as fh:
        fh.write("nameserver 127.0.0.1\n")

    yield

    with open("/etc/resolv.conf", 'wb') as fh:
        fh.write(old)


@pytest.fixture(scope='session')
def nginx_class(repo_is_ee, dns_mock, log_catcher, syslog_mock, mocker_s):
    """Provide a Nginx class suitable for the repository flavour

    This fixture also binds together all the mocks (dns, syslog, mocker(endpoints),
    log_catcher), so that tests developer can spawn it's own AR instance if
    the default ones (master_ar_process/agent_ar_process) are insufficient.
    """
    if repo_is_ee:
        from runner.ee import Nginx
    else:
        from runner.open import Nginx

    def f(*args, role="master", **kwargs):
        # We cannot define it as a fixture due to the fact that nginx_class is
        # used both in other fixtures and in tests directly. Liten link setup
        # fixture would have to be pulled in every time nginx_class is used
        # on its own.
        ar_listen_link_setup(role, repo_is_ee)
        return Nginx(*args, role=role, log_catcher=log_catcher, **kwargs)

    return f


@pytest.fixture(scope='module')
def master_ar_process(nginx_class):
    """A go-to AR process instance fixture that should be used in most of the
    tests.

    We cannot have 'session' scoped AR processes, as some of the tests will
    need to start AR with different env vars or AR type (master/agent). So the
    idea is to give it 'module' scope and thus have the same AR instance for
    all the tests in given test file unless some greater flexibility is required
    and the nginx_class fixture is used directly.
    """
    nginx = nginx_class(role="master")
    nginx.start()

    yield nginx

    nginx.stop()


@pytest.fixture(scope='module')
def agent_ar_process(nginx_class):
    """
    Same as `master_ar_process` fixture except for the fact that it starts 'agent'
    nginx instead of `master`.
    """
    nginx = nginx_class(role="agent")
    nginx.start()

    yield nginx

    nginx.stop()


@pytest.fixture(scope='session')
def valid_jwt_generator(repo_is_ee):
    """Generate valid JWT for given repository flavour and parameters

    ATM Open uses HS256, while EE: RS256. This fixture abstracts it away by
    providing transparent interface to generating valid JWTs for given repository
    flavour.

    This fixture exposes interface where it is possible to manipulate resulting
    JWT field values.
    """
    if repo_is_ee:
        key_path = os.getenv('IAM_PRIVKEY_FILE_PATH')
    else:
        key_path = os.getenv('IAM_SHARED_SECRET_FILE_PATH')

    assert key_path is not None

    if repo_is_ee:
        def f(uid, *args, **kwargs):
            return generate_rs256_jwt(key_path, uid=uid, *args, **kwargs)
    else:
        def f(uid, *args, **kwargs):
            return generate_hs256_jwt(key_path, uid=uid, *args, **kwargs)

    return f


@pytest.fixture(scope='session')
def superuser_user_header(valid_jwt_generator):
    """This fixture further simplifies JWT handling by providing a ready-to-use
    headers with a valid  superuser JSON Web Token for `requests` module to
    use"""
    token = valid_jwt_generator(uid='root')
    header = {'Authorization': 'token={}'.format(token)}

    return header


@pytest.fixture(scope='session')
def valid_user_header(valid_jwt_generator):
    """This fixture further simplifies JWT handling by providing a ready-to-use
    headers with a valid JSON Web Token for `requests` module to use"""
    token = valid_jwt_generator(uid='bozydar')
    header = {'Authorization': 'token={}'.format(token)}

    return header


@pytest.fixture(scope='session')
def invalid_user_header(valid_jwt_generator):
    """This fixture further simplifies JWT handling by providing a ready-to-use
    headers with an invalid JSON Web Token for `requests` module to use. This
    can be useful while testing if i.e. access is denied to unknown user to some
    resource."""
    token = valid_jwt_generator(uid='foobar')
    header = {'Authorization': 'token={}'.format(token)}

    return header
