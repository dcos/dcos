"""
Test Enterprise DC/OS Signal Service
TODO: this test only differs from upstream in the services that it checks for, rather
    find a method such that we do not need to duplicate so much code
"""
import json
import logging
import os
import subprocess
from pathlib import Path

from dcos_test_utils.dcos_api import DcosApiSession
from test_helpers import get_expanded_config

__maintainer__ = 'mnaboka'
__contact__ = 'dcos-cluster-ops@mesosphere.io'


log = logging.getLogger(__name__)


def test_signal_service(dcos_api_session: DcosApiSession) -> None:
    """
    signal-service runs on an hourly timer, this test runs it as a one-off
    and pushes the results to the test_server app for easy retrieval

    When this test fails due to `dcos-checks-poststart-service-unhealthy`,
    consider that the issue may be due to timeouts which are too low.  See
    https://jira.mesosphere.com/browse/DCOS-22458 for more information.
    """
    dcos_version = os.getenv("DCOS_VERSION", "")
    variant = 'open'

    signal_config_path = Path('/opt/mesosphere/etc/dcos-signal-config.json')
    signal_config = json.loads(signal_config_path.read_text())
    signal_extra_path = Path('/opt/mesosphere/etc/dcos-signal-extra.json')
    try:
        signal_config.update(json.loads(signal_extra_path.read_text()))
        variant = 'enterprise'
    except FileNotFoundError:
        # the file only exists on EE clusters so just skip if it's not there
        pass

    customer_key = signal_config.get('customer_key', '')
    cluster_id = Path('/var/lib/dcos/cluster-id').read_text().strip()

    # sudo is required to read /run/dcos/etc/signal-service/service_account.json
    env = os.environ.copy()
    signal_cmd = ["sudo", "-E", "/opt/mesosphere/bin/dcos-signal", "-test"]
    # universal_newlines means utf-8
    with subprocess.Popen(signal_cmd, stdout=subprocess.PIPE, universal_newlines=True, env=env) as p:
        signal_results = p.stdout.read()  # type: ignore

    r_data = json.loads(signal_results)

    # Collect the dcos-diagnostics output that `dcos-signal` uses to determine
    # whether or not there are failed units.
    resp = dcos_api_session.get('/system/health/v1/report?cache=0')
    # We expect reading the health report to succeed.
    resp.raise_for_status()
    # Parse the response into JSON.
    health_report = resp.json()
    # Reformat the /health json into the expected output format for dcos-signal.
    units_health = {}
    for unit, unit_health in health_report["Units"].items():
        unhealthy = 0
        for node_health in unit_health["Nodes"]:
            for output_unit, output in node_health["Output"].items():
                if unit != output_unit:
                    # This is the output of some unrelated unit, ignore.
                    continue
                if output == "":
                    # This unit is healthy on this node.
                    pass
                else:
                    # This unit is unhealthy on this node.
                    unhealthy += 1
        prefix = "health-unit-{}".format(unit.replace('.', '-'))
        units_health.update({
            "{}-total".format(prefix): len(unit_health["Nodes"]),
            "{}-unhealthy".format(prefix): unhealthy,
        })

    exp_data = {
        'diagnostics': {
            'event': 'health',
            'anonymousId': cluster_id,
            'properties': units_health,
        },
        'cosmos': {
            'event': 'package_list',
            'anonymousId': cluster_id,
            'properties': {}
        },
        'mesos': {
            'event': 'mesos_track',
            'anonymousId': cluster_id,
            'properties': {}
        }
    }

    if customer_key != '':
        exp_data['diagnostics']['userId'] = customer_key

    dcos_config = get_expanded_config()
    # Generic properties which are the same between all tracks
    generic_properties = {
        'licenseId': '',
        'platform': dcos_config['platform'],
        'provider': dcos_config['provider'],
        'source': 'cluster',
        'clusterId': cluster_id,
        'customerKey': customer_key,
        'environmentVersion': dcos_version,
        'variant': variant
    }

    # Insert the generic property data which is the same between all signal tracks
    exp_data['diagnostics']['properties'].update(generic_properties)   # type: ignore
    exp_data['cosmos']['properties'].update(generic_properties)  # type: ignore
    exp_data['mesos']['properties'].update(generic_properties)  # type: ignore

    # Check the entire hash of diagnostics data
    if r_data['diagnostics'] != exp_data['diagnostics']:
        # The optional second argument to `assert` is an error message that
        # appears to get truncated in the output. As such, we log the output
        # instead.
        log.error("Cluster is unhealthy: {}".format(
            json.dumps(health_report, indent=4, sort_keys=True)))
        assert r_data['diagnostics'] == exp_data['diagnostics']

    # Check a subset of things regarding Mesos that we can logically check for
    framework_names = [x['name'] for x in r_data['mesos']['properties']['frameworks']]
    assert 'marathon' in framework_names
    assert 'metronome' in framework_names

    # There are no packages installed by default on the integration test, ensure the key exists
    assert len(r_data['cosmos']['properties']['package_list']) == 0
