"""This file has only one function: to provide a correctly configured
ClusterApi object that will be injected into the pytest 'cluster' fixture
via the make_cluster_fixture() method
"""
from test_util.cluster_api import ClusterApi, get_args_from_env
from test_util.helpers import CI_AUTH_JSON, DcosUser


def make_cluster_fixture():
    args = get_args_from_env()
    args['web_auth_default_user'] = DcosUser(CI_AUTH_JSON)
    cluster_api = ClusterApi(**args)
    cluster_api.wait_for_dcos()
    return cluster_api
