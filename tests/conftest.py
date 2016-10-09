import os

import pytest

import gen.calc


@pytest.fixture(autouse=True)
def mock_installer_latest_complete_artifact(monkeypatch):
    monkeypatch.setattr(
        gen.calc,
        'installer_latest_complete_artifact',
        lambda: {'bootstrap': os.getenv('BOOTSTRAP_ID', '12345'), 'packages': []},
    )
