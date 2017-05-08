"""This file has only one function: to provide a correctly configured
DcosApiSession object that will be injected into the pytest 'dcos_api_session' fixture
via the make_session_fixture() method
"""
from test_helpers import expanded_config

from test_util.dcos_api_session import DcosApiSession, DcosUser, get_args_from_env
from test_util.helpers import CI_CREDENTIALS


def make_session_fixture():
    args = get_args_from_env()

    exhibitor_admin_password = None
    if expanded_config['exhibitor_admin_password_enabled'] == 'true':
        exhibitor_admin_password = expanded_config['exhibitor_admin_password']

    dcos_api_session = DcosApiSession(
        auth_user=DcosUser(CI_CREDENTIALS),
        exhibitor_admin_password=exhibitor_admin_password,
        **args)
    dcos_api_session.wait_for_dcos()
    return dcos_api_session
