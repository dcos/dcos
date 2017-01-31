import os

import pytest

import gen.build_deploy.bash


@pytest.fixture(autouse=True)
def mock_installer_latest_complete_artifact(monkeypatch):
    monkeypatch.setattr(
        gen.build_deploy.bash,
        'installer_latest_complete_artifact',
        lambda: {'bootstrap': os.getenv('BOOTSTRAP_ID', '12345'), 'packages': []},
    )
