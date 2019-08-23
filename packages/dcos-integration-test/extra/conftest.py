import datetime
import logging
import os
import sys

import env_helper

import pytest
import requests
from _pytest.tmpdir import TempdirFactory
from dcos_test_utils import dcos_cli
from dcos_test_utils.diagnostics import Diagnostics
from test_helpers import get_expanded_config

log = logging.getLogger(__name__)

pytest_plugins = ['pytest-dcos']


@pytest.fixture(scope='session')
def dcos_api_session(dcos_api_session_factory):
    """ Overrides the dcos_api_session fixture to use
    exhibitor settings currently used in the cluster
    """
    args = dcos_api_session_factory.get_args_from_env()

    exhibitor_admin_password = None
    expanded_config = get_expanded_config()
    if expanded_config['exhibitor_admin_password_enabled'] == 'true':
        exhibitor_admin_password = expanded_config['exhibitor_admin_password']

    api = dcos_api_session_factory(
        exhibitor_admin_password=exhibitor_admin_password,
        **args)
    api.wait_for_dcos()
    return api


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
            env_string = '//env:PYTEST_LOCALE=en_US.utf8'
            options = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
            key_path = os.getenv('DCOS_SSH_KEY_PATH')
            if key_path:
                options += '-i ' + key_path
            for k, v in env_vars.items():
                env_string += '//env:{}={}'.format(k, v)
                config.option.tx = [
                    'ssh={options} {DCOS_SSH_USER}@{master_ip}//python=/opt/mesosphere/bin/dcos-shell '
                    'python{env_string}'
                    .format(
                        options=options, DCOS_SSH_USER=env_vars['DCOS_SSH_USER'], env_string=env_string,
                        master_ip=env_vars['MASTER_PUBLIC_IP']
                    )
                ]
        if not config.option.rsyncdir:
            config.option.rsyncdir = [os.path.dirname(os.path.abspath(__file__))]


def pytest_addoption(parser):
    parser.addoption("--windows-only", action="store_true",
                     help="run only Windows tests")
    parser.addoption("--env-help", action="store_true",
                     help="show which environment variables must be set for DC/OS integration tests")


def pytest_configure(config):
    config.addinivalue_line('markers', 'first: run test before all not marked first')
    config.addinivalue_line('markers', 'last: run test after all not marked last')


def pytest_collection_modifyitems(session, config, items):
    """Reorders test using order mark
    """
    new_items = []
    last_items = []
    for item in items:
        if config.getoption('--windows-only'):
            if item.get_closest_marker('supportedwindows') is None:
                continue
        elif item.get_closest_marker('supportedwindowsonly') is not None:
            continue

        if hasattr(item.obj, 'first'):
            new_items.insert(0, item)
        elif hasattr(item.obj, 'last'):
            last_items.append(item)
        else:
            new_items.append(item)
    items[:] = new_items + last_items


def _purge_marathon_nofail(session):
    """
    Try to clean Marathon.
    Do not error if there is a problem.
    """
    try:
        session.marathon.purge()
    except Exception as exc:
        log.exception('Ignoring exception during marathon.purge(): %s', exc)
        if isinstance(exc, requests.exceptions.HTTPError):
            log.error('exc.response.text: %s', exc.response.text)


# Note(JP): Attempt to reset Marathon state before and after every test module
# run in this test suite. This is a brute force approach but we found that the
# problem of side effects as of too careless test isolation and resource
# cleanup became too large.
#
# Note: This is module-scoped so that we can have module- and class-scoped
# fixtures which create Marathon resources.
# The trade-off here is that tests, in particular failing tests, can leak
# resources within a module.
@pytest.fixture(autouse=True, scope='module')
def clean_marathon_state(dcos_api_session):
    """
    Attempt to clean up Marathon state before entering the test module and when
    leaving the test module. Especially attempt to clean up when the test code
    failed. When the cleanup fails do not fail the test but log relevant
    information.
    """
    _purge_marathon_nofail(session=dcos_api_session)
    try:
        yield
    finally:
        _purge_marathon_nofail(session=dcos_api_session)


@pytest.fixture(autouse=False, scope='function')
def clean_marathon_state_function_scoped(dcos_api_session):
    """
    See ``clean_marathon_state`` - this is function scoped as some test modules
    require cleanup after every test.
    """
    _purge_marathon_nofail(session=dcos_api_session)
    try:
        yield
    finally:
        _purge_marathon_nofail(session=dcos_api_session)


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
        creation_start = datetime.datetime.now()
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

        duration = last_datapoint['time'] - creation_start
        log.info('\nDiagnostis bundle took {} to generate'.format(duration))

        log.info('\nWait for diagnostics report to become available')
        diagnostics.wait_for_diagnostics_reports()

        log.info('\nDownload zipped diagnostics reports')
        bundles = diagnostics.get_diagnostics_reports()
        diagnostics.download_diagnostics_reports(diagnostics_bundles=bundles)
    else:
        log.info('\nNot downloading diagnostics bundle for this session.')


@pytest.fixture(scope='session')
def install_dcos_cli(tmpdir_factory: TempdirFactory):
    """
    Install the CLI.
    """
    tmpdir = tmpdir_factory.mktemp('dcos_cli')
    cli = dcos_cli.DcosCli.new_cli(
        download_url='https://downloads.dcos.io/cli/releases/binaries/dcos/linux/x86-64/latest/dcos',
        core_plugin_url='https://downloads.dcos.io/cli/releases/plugins/dcos-core-cli/linux/x86-64/dcos-core-cli-1.14-patch.2.zip',  # noqa: E501
        ee_plugin_url='https://downloads.mesosphere.io/cli/releases/plugins/dcos-enterprise-cli/linux/x86-64/dcos-enterprise-cli-1.13-patch.1.zip',  # noqa: E501
        tmpdir=str(tmpdir)
    )
    yield cli
    cli.clear_cli_dir()


@pytest.fixture
def new_dcos_cli(install_dcos_cli: dcos_cli.DcosCli) -> dcos_cli.DcosCli:
    """
    Ensure there is no CLI state from a previous test.
    """
    install_dcos_cli.clear_cli_dir()
    return install_dcos_cli
