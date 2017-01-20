"""This file has only one function: to provide a correctly configured
DcosApiSession object that will be injected into the pytest 'cluster' fixture
via the make_cluster_fixture() method
"""
from test_util.dcos_api_session import DcosApiSession, DcosUser, get_args_from_env
from test_util.helpers import CI_CREDENTIALS


def make_cluster_fixture():
    args = get_args_from_env()
    args['auth_user'] = DcosUser(CI_CREDENTIALS)
    cluster_api = DcosApiSession(**args)
    cluster_api.wait_for_dcos()
    return cluster_api
