"""
Testing the CockroachDB setup in DC/OS.
"""
import logging
import subprocess

from retrying import retry


__maintainer__ = 'tweidner'
__contact__ = 'security-team@mesosphere.io'


LOG = logging.getLogger(__name__)


def test_config_change_applied() -> None:
    config_change_unit = 'dcos-cockroachdb-config-change'
    subprocess.check_call(
        ['sudo', 'systemctl', 'restart', config_change_unit],
    )
    assert _wait_for_expected_journal_output(
        # Indicator for successful config update via CRDB SQL client.
        expected_output='CONFIGURE ZONE 1',
        unit=config_change_unit,
    )


@retry(
    stop_max_delay=30000,
    wait_fixed=1000,
    retry_on_result=lambda x: not x,
)
def _wait_for_expected_journal_output(expected_output: str, unit: str) -> bool:
    result = subprocess.check_output(
        ['sudo', 'journalctl', '-u', unit, '--no-pager'],
        universal_newlines=True,
    )
    return expected_output in result
