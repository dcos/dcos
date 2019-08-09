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
