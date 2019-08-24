import os
import sys

import api_session_fixture
import env_helper
import pytest
from dcos_test_utils import logger

logger.setup(os.getenv('TEST_LOG_LEVEL', 'INFO'))


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
    try:
        parser.addoption("--env-help", action="store_true",
                         help="show which environment variables must be set for DC/OS integration tests")
    except ValueError:
        # When running open source tests on an enterprise cluster version <=1.11, pytest attempts to load --env-help
        # twice from the open + ee conftests, which throws a ValueError (it can only be loaded once). This error most
        # likely occurs because of residual .pyc files. Since this is a corner case and only happens on 1.11 and below,
        # we simply ignore the error so that we only add the option once.
        pass


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


@pytest.fixture(autouse=True)
def clean_marathon_state(dcos_api_session):
    dcos_api_session.marathon.purge()
    yield
    dcos_api_session.marathon.purge()


@pytest.fixture(scope='session')
def dcos_api_session():
    return api_session_fixture.make_session_fixture()


@pytest.fixture(scope='session')
def noauth_api_session(dcos_api_session):
    return dcos_api_session.get_user_session(None)
