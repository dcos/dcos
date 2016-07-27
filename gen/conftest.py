import os

import pytest

import dcos_installer.config_util


@pytest.fixture(autouse=True)
def mock_installer_latest_complete_artifact(monkeypatch):
    monkeypatch.setattr(
        dcos_installer.config_util,
        'installer_latest_complete_artifact',
        lambda: {'bootstrap': os.getenv('BOOTSTRAP_ID', '12345'), 'packages': []},
    )
