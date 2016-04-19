import os

from dcos_installer import async_server


def test_unlink_state_file(monkeypatch):
    monkeypatch.setattr(os.path, 'isfile', lambda x: True)

    def mocked_unlink(path):
        assert path == '/genconf/state/preflight.json'

    monkeypatch.setattr(os, 'unlink', mocked_unlink)
    async_server.unlink_state_file('preflight')
