import logging
import os
import sys

import api_session_fixture
import env_helper
import pytest
import requests

from dcos_test_utils import logger
from dcos_test_utils.diagnostics import Diagnostics

logger.setup(os.getenv('TEST_LOG_LEVEL', 'INFO'))
log = logging.getLogger(__name__)


def pytest_configure(config):
    config.addinivalue_line('markers', 'first: run test before all not marked first')
    config.addinivalue_line('markers', 'last: run test after all not marked last')


def pytest_cmdline_main(config):
    user_outside_cluster = True
    if os.path.exists('/opt/mesosphere/bin/dcos-shell'):
        user_outside_cluster = False

    if user_outside_cluster and config.option.env_help:
        print(env_helper.HELP_MESSAGE)
        sys.exit()

    if user_outside_cluster and not config.option.help and not config.option.collectonly:
        env_vars = env_helper.get_env_vars()
        if config.option.dist == 'no':
            config.option.dist = 'load'
        if not config.option.tx:
            env_string = ''
            options = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
            key_path = os.getenv('SSH_KEY_PATH')
            if key_path:
                options += '-i ' + key_path
            for k, v in env_vars.items():
                env_string += '//env:{}={}'.format(k, v)
                config.option.tx = ['ssh={options} {ssh_user}@{master_ip}//python=dcos-shell python{env_string}'.format(
                    options=options, ssh_user=env_vars['SSH_USER'], master_ip=env_vars['MASTER_PUBLIC_IP'],
                    env_string=env_string)]
        if not config.option.rsyncdir:
            config.option.rsyncdir = [os.path.dirname(os.path.abspath(__file__))]


def pytest_addoption(parser):
    parser.addoption("--env-help", action="store_true",
                     help="show which environment variables must be set for DC/OS integration tests")


def pytest_collection_modifyitems(session, config, items):
    """Reorders test using order mark
    """
    new_items = []
    last_items = []
    for item in items:
        if hasattr(item.obj, 'first'):
            new_items.insert(0, item)
        elif hasattr(item.obj, 'last'):
            last_items.append(item)
        else:
            new_items.append(item)
    items[:] = new_items + last_items


# Note(JP): Attempt to reset Marathon state before and after every test run in
# this test suite. This is a brute force approach but we found that the problem
# of side effects as of too careless test isolation and resource cleanup became
# too large. If this test suite ever introduces a session- or module-scoped
# fixture providing a Marathon app then the `autouse=True` approach will need to
# be relaxed.
@pytest.fixture(autouse=True)
def clean_marathon_state(dcos_api_session):
    """
    Attempt to clean up Marathon state before entering the test and when leaving
    the test. Especially attempt to clean up when the test code failed. When the
    cleanup fails do not fail the test but log relevant information.
    """

    def _purge_nofail():
        try:
            dcos_api_session.marathon.purge()
        except Exception as exc:
            log.exception('Ignoring exception during marathon.purge(): %s', exc)
            if isinstance(exc, requests.exceptions.HTTPError):
                log.error('exc.response.text: %s', exc.response.text)

    _purge_nofail()
    try:
        yield
    finally:
        _purge_nofail()


@pytest.fixture(scope='session')
def dcos_api_session():
    return api_session_fixture.make_session_fixture()


@pytest.fixture(scope='session')
def noauth_api_session(dcos_api_session):
    return dcos_api_session.get_user_session(None)


@pytest.fixture(scope='session', autouse=True)
def _dump_diagnostics(request, dcos_api_session):
    """Download the zipped diagnostics bundle report from each master in the cluster to the home directory. This should
    be run last. The _ prefix makes sure that pytest calls this first out of the autouse session scope fixtures, which
    means that its post-yield code will be executed last.

    * There is no official way to ensure fixtures are called in a certain order
    https://github.com/pytest-dev/pytest/issues/1216
    * However it seems that fixtures at the same scope are called alphabetically
    https://stackoverflow.com/a/28593102/1436300
    """
    yield

    make_diagnostics_report = os.environ.get('DIAGNOSTICS_DIRECTORY') is not None
    if make_diagnostics_report:
        last_datapoint = {
            'time': None,
            'value': 0
        }

        health_url = dcos_api_session.default_url.copy(
            query='cache=0',
            path='system/health/v1',
        )

        diagnostics = Diagnostics(
            default_url=health_url,
            masters=dcos_api_session.masters,
            all_slaves=dcos_api_session.all_slaves,
            session=dcos_api_session.copy().session,
        )

        log.info('Create diagnostics report for all nodes')
        diagnostics.start_diagnostics_job()

        log.info('\nWait for diagnostics job to complete')
        diagnostics.wait_for_diagnostics_job(last_datapoint=last_datapoint)

        log.info('\nWait for diagnostics report to become available')
        diagnostics.wait_for_diagnostics_reports()

        log.info('\nDownload zipped diagnostics reports')
        bundles = diagnostics.get_diagnostics_reports()
        diagnostics.download_diagnostics_reports(diagnostics_bundles=bundles)
    else:
        log.info('\nNot downloading diagnostics bundle for this session.')
