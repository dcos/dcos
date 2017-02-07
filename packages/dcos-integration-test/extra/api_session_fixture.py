"""This file has only one function: to provide a correctly configured
DcosApiSession object that will be injected into the pytest 'dcos_api_session' fixture
via the make_session_fixture() method
"""
from test_util.dcos_api_session import DcosApiSession, DcosUser, get_args_from_env
from test_util.helpers import CI_CREDENTIALS


def make_session_fixture():
    args = get_args_from_env()
    args['auth_user'] = DcosUser(CI_CREDENTIALS)
    dcos_api_session = DcosApiSession(**args)
    dcos_api_session.wait_for_dcos()
    return dcos_api_session
