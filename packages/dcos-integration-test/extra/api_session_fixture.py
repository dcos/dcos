"""This file has only one function: to provide a correctly configured
ClusterApi object that will be injected into the pytest 'dcos_api_session' fixture
via the make_dcos_api_session_fixture() method
"""
from test_util.cluster_api import ClusterApi, get_args_from_env
from test_util.helpers import CI_AUTH_JSON, DcosUser


def make_session_fixture():
    args = get_args_from_env()
    args['web_auth_default_user'] = DcosUser(CI_AUTH_JSON)
    dcos_api_session = ClusterApi(**args)
    dcos_api_session.wait_for_dcos()
    return dcos_api_session
