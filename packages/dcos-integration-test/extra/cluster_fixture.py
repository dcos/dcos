"""This file has only one function: to provide a correctly configured
ClusterApi object that will be injected into the pytest 'cluster' fixture
via the make_cluster_fixture() method
"""
import os

from pkgpanda.util import load_json
from test_util.cluster_api import ClusterApi, get_args_from_env
from test_util.helpers import DcosUser


def make_cluster_fixture():
    # token valid until 2036 for user albert@bekstil.net
    # {
    #   "email": "albert@bekstil.net",
    #   "email_verified": true,
    #   "iss": "https://dcos.auth0.com/",
    #   "sub": "google-oauth2|109964499011108905050",
    #   "aud": "3yF5TOSzdlI45Q1xspxzeoGBe9fNxm9m",
    #   "exp": 2090884974,
    #   "iat": 1460164974
    # }
    auth_json = {'token': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImtpZCI6Ik9UQkVOakZFTWtWQ09VRTRPRVpGTlRNMFJrWXlRa015Tnprd1JrSkVRemRCTWpBM1FqYzVOZyJ9.eyJlbWFpbCI6ImFsYmVydEBiZWtzdGlsLm5ldCIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJpc3MiOiJodHRwczovL2Rjb3MuYXV0aDAuY29tLyIsInN1YiI6Imdvb2dsZS1vYXV0aDJ8MTA5OTY0NDk5MDExMTA4OTA1MDUwIiwiYXVkIjoiM3lGNVRPU3pkbEk0NVExeHNweHplb0dCZTlmTnhtOW0iLCJleHAiOjIwOTA4ODQ5NzQsImlhdCI6MTQ2MDE2NDk3NH0.OxcoJJp06L1z2_41_p65FriEGkPzwFB_0pA9ULCvwvzJ8pJXw9hLbmsx-23aY2f-ydwJ7LSibL9i5NbQSR2riJWTcW4N7tLLCCMeFXKEK4hErN2hyxz71Fl765EjQSO5KD1A-HsOPr3ZZPoGTBjE0-EFtmXkSlHb1T2zd0Z8T5Z2-q96WkFoT6PiEdbrDA-e47LKtRmqsddnPZnp0xmMQdTr2MjpVgvqG7TlRvxDcYc-62rkwQXDNSWsW61FcKfQ-TRIZSf2GS9F9esDF4b5tRtrXcBNaorYa9ql0XAWH5W_ct4ylRNl3vwkYKWa4cmPvOqT5Wlj9Tf0af4lNO40PQ'}  # noqa
    if 'DCOS_AUTH_JSON_PATH' in os.environ:
        auth_json = load_json(os.environ['DCOS_AUTH_JSON_PATH'])
    args = get_args_from_env()
    args['web_auth_default_user'] = DcosUser(auth_json)
    cluster_api = ClusterApi(**args)
    cluster_api.wait_for_dcos()
    return cluster_api
