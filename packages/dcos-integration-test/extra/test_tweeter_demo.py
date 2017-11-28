import logging
import os

import pytest
import requests
import retrying

import test_helpers

from test_packaging import (
    skipif_insufficient_resources
)

log = logging.getLogger(__name__)

DEMO_RESOURCE_REQUIREMENTS = {
    'number_of_nodes': 5,
    'node': {
        'disk': 0,
        'mem': 0,
        'cpus': 1
    }
}


def _get_tweeter_app_definition():
    response = requests.get('https://raw.githubusercontent.com/mesosphere/tweeter/master/tweeter.json')
    return response.json()


def _get_post_tweets_app_definition():
    response = requests.get('https://raw.githubusercontent.com/mesosphere/tweeter/master/post-tweets.json')
    return response.json()


def _get_tweet_count(address):
    """Count the number of tweets on the tweeter app's webpage

    Args:
        address: str URL
    """
    response = requests.get(address)
    log.info('tweeter status: {}'.format(response.status_code))
    return response.text.count('tweet-content')


@retrying.retry(
    wait_fixed=(10 * 1000),
    stop_max_delay=(10 * 60 * 1000))
def _wait_for_tweet_count(url):
    # This is 25 tweets because of how paging in tweeter is defined
    assert _get_tweet_count(url) == 25, "Did not find expected 25 tweets"


@pytest.mark.skipif(
    test_helpers.expanded_config.get('security') in ('disabled', 'permissive', 'strict'),
    reason='Enterprise tweeter tests in test_tweeter_demo_enterprise.py')
def test_tweeter_demo(dcos_api_session):
    """Step through setup and run the Tweeter demo application. See https://github.com/mesosphere/tweeter
    Should be equivalent to the cli script. It passes if service and app installations are successful and the
    post_tweets application successfully posts tweets to the tweeter webapp.

    Service versions are read through environment variables set through the Tweeter Demo job on TeamCity. These default
    to None, so cosmos/packaging will install the most recent version of the service compatible with the version of
    DC/OS being used.

    Differences from tutorial:
     - does not install and run Zeppelin (notebook analytics)
     - accesses the tweeter app via the virtual IP instead of the public ELB endpoint
    """
    skipif_insufficient_resources(dcos_api_session, DEMO_RESOURCE_REQUIREMENTS)

    dependencies = {
        'cassandra': os.environ.get('CASSANDRA_VERSION'),
        'kafka': os.environ.get('KAFKA_VERSION'),
        'marathon-lb': os.environ.get('MARATHON_LB_VERSION')
    }

    for service, version in dependencies.items():
        log.info("Installing {0} {1}".format(service, version or "(most recent version)"))
        dcos_api_session.cosmos.install_package(service, version)

    log.info("Waiting for requirements to deploy")
    dcos_api_session.marathon.wait_for_deployments_complete()

    tweeter_app_definition = _get_tweeter_app_definition()
    log.info("Deploying tweeter")
    log.debug("Using tweeter app definition: " + str(tweeter_app_definition))
    # app instances have an 'unhealthy' stage before transitioning to healthy, which would cause this to fail every time
    # even if it ultimately would have successfully deployed
    dcos_api_session.marathon.deploy_app(tweeter_app_definition, check_health=False)

    post_tweets_definition = _get_post_tweets_app_definition()
    log.info("Deploying post_tweets")
    log.debug(post_tweets_definition)
    # post-tweets does not define a health check
    dcos_api_session.marathon.deploy_app(post_tweets_definition, check_health=False)

    # The tutorial has you use the public endpoint, but this test is run from the cluster itself, so the app can simply
    # be accessed from the private endpoint as configured in the app definition.
    url = 'http://' + tweeter_app_definition['container']['docker']['portMappings'][0]['labels']['VIP_0']
    _wait_for_tweet_count(url)
