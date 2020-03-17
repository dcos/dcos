from pathlib import Path

import pytest

from common import exceptions, storage
from core import command, cmdconf


@cmdconf.cmdconf_type('test')
class SetupConf:

    def __init__(self, **cmd_opts):
        self._opts = cmd_opts

    def __getattr__(self, name):
        return self._opts[name]


class TestCommandState:

    def test_save_load_remove(self, tmp_path: Path):
        """
        State file can be set and unset.
        """
        filename = tmp_path / 'state'
        state = '\u0394STATE\n'
        cs = command.CommandState(str(filename))
        cs.set_state(state)
        assert filename.exists()
        assert cs.get_state() == state
        cs.unset_state()
        assert not filename.exists()
        assert cs.get_state() is None

    def test_save_no_parent(self, tmp_path: Path):
        """
        State file can be set when directory does not exist.
        """
        filename = tmp_path / 'not_exist' / 'state'
        state = '\u0394STATE\n'
        cs = command.CommandState(str(filename))
        cs.set_state(state)
        assert cs.get_state() == state

    def test_remove_non_existent(self, tmp_path: Path):
        """
        State file can be unset when file does not exist.
        """
        filename = tmp_path / 'state'
        cs = command.CommandState(str(filename))
        assert not filename.exists()
        cs.unset_state()


class TestCommandSetup:

    def test_command_detect_state(self, tmp_path: Path):
        """
        winpanda setup command fails if a state file is found,
        indicating that a previous setup/upgrade has failed.
        """
        setup = command.CmdSetup(
            command_name='test',
            command_target='pkgall',
            inst_storage=storage.InstallationStorage(
                root_dpath=str(tmp_path / 'root')
            ),
        )

        existing_state = 'RanDOm'
        setup.state.set_state(existing_state)

        # Installation fails due to existing state
        with pytest.raises(exceptions.InstallationError) as e:
            setup.execute()

        # Error message mentions found state
        assert existing_state in e.value.args[0]

    def test_command_detect_bindir(self, tmp_path: Path):
        """
        winpanda setup command fails if a bin directory is found,
        indicating that a previous setup has installed files.
        """
        setup = command.CmdSetup(
            command_name='test',
            command_target='pkgall',
            inst_storage=storage.InstallationStorage(
                root_dpath=str(tmp_path / 'root')
            ),
        )

        varlib = tmp_path / 'root' / 'var' / 'lib'
        varlib.mkdir(parents=True)
        cluster_id = varlib / 'cluster-id'
        cluster_id.write_text('cluster-id')

        # Installation fails due to existing cluster-id
        with pytest.raises(exceptions.InstallationError) as e:
            setup.execute()

        # Error message mentions cluster-id path
        assert str(cluster_id) in e.value.args[0]
