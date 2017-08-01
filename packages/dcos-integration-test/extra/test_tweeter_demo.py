from functools import wraps

import pytest

from test_packaging import (
    _skipif_insufficient_resources,
    _install_and_verify_app
)

# TODO
DEMO_RESOURCE_REQUIREMENTS = {
    'number_of_nodes': 5,
    'node': {
        'disk': 0,
        'mem': 0,
        'cpus': 1
    }
}

CASSANDRA_STABLE_VERSION = '1.0.12-2.2.5'
KAFKA_STABLE_VERSION = '1.1.9-0.10.0.0'


def test_tweeter_demo_OSS(dcos_api_session):
    """
    """

    _skipif_insufficient_resources(dcos_api_session, DEMO_RESOURCE_REQUIREMENTS)

    _install_and_verify_app('cassandra', CASSANDRA_STABLE_VERSION)
    _install_and_verify_app('kafka', KAFKA_STABLE_VERSION)
    # TODO: The version of this depends on the cluster version - handle cases
    _install_and_verify_app('marathon-lb')


# TODO enterprise test
