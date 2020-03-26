from pathlib import Path

import pytest

from common import exceptions, storage
from core import command, cmdconf


@cmdconf.cmdconf_type('test')
class CommandConf:

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
        cmd = command.CmdSetup(
            command_name='test',
            command_target='pkgall',
            inst_storage=storage.InstallationStorage(
                root_dpath=str(tmp_path / 'root')
            ),
        )

        existing_state = 'RanDOm'
        cmd.state.set_state(existing_state)

        # Installation fails due to existing state
        with pytest.raises(exceptions.InstallationError) as e:
            cmd.execute()

        # Error message mentions found state
        assert existing_state in e.value.args[0]

    def test_command_detect_cluster(self, tmp_path: Path):
        """
        winpanda setup command fails if an existing cluster is found,
        indicating that a previous setup has installed files.
        """
        cmd = command.CmdSetup(
            command_name='test',
            command_target='pkgall',
            inst_storage=storage.InstallationStorage(
                root_dpath=str(tmp_path / 'root')
            ),
        )

        bindir = tmp_path / 'root' / 'bin'
        bindir.mkdir(parents=True)
        mesos_exe = bindir / 'mesos-agent.exe'
        mesos_exe.write_text('fake')

        # Installation fails due to existing cluster
        with pytest.raises(exceptions.InstallationError) as e:
            cmd.execute()

        # Error message mentions mesos-agent.exe
        assert str(mesos_exe) in e.value.args[0]


class TestCommandUpgrade:

    def test_command_detect_state(self, tmp_path: Path):
        """
        winpanda upgrade command fails if a state file is found,
        indicating that a previous setup/upgrade has failed.
        """
        cmd = command.CmdUpgrade(
            command_name='test',
            command_target='pkgall',
            inst_storage=storage.InstallationStorage(
                root_dpath=str(tmp_path / 'root')
            ),
        )

        existing_state = 'RanDOm'
        cmd.state.set_state(existing_state)

        # Installation fails due to existing state
        with pytest.raises(exceptions.InstallationError) as e:
            cmd.execute()

        # Error message mentions found state
        assert existing_state in e.value.args[0]

    def test_command_detect_cluster(self, tmp_path: Path):
        """
        winpanda upgrade command fails if a valid cluster is not found.
        """
        cmd = command.CmdUpgrade(
            command_name='test',
            command_target='pkgall',
            inst_storage=storage.InstallationStorage(
                root_dpath=str(tmp_path / 'root')
            ),
        )

        bindir = tmp_path / 'root' / 'bin'
        bindir.mkdir(parents=True)
        mesos_exe = bindir / 'mesos-agent.exe'

        # Installation fails due to non-existing Mesos agent
        with pytest.raises(exceptions.InstallationError) as e:
            cmd.execute()

        # Error message mentions Mesos agent path
        assert str(mesos_exe) in e.value.args[0]


class TestCommandStart:

    def test_command_detect_state(self, tmp_path: Path):
        """
        winpanda start command fails if a state file is found,
        indicating that a previous setup/upgrade has failed.
        """
        cmd = command.CmdStart(
            command_name='test',
            command_target='pkgall',
            inst_storage=storage.InstallationStorage(
                root_dpath=str(tmp_path / 'root')
            ),
        )

        existing_state = 'RanDOm'
        cmd.state.set_state(existing_state)

        # Installation fails due to existing state
        with pytest.raises(exceptions.InstallationError) as e:
            cmd.execute()

        # Error message mentions found state
        assert existing_state in e.value.args[0]

    def test_command_detect_cluster(self, tmp_path: Path):
        """
        winpanda start command fails if a valid cluster is not found.
        """
        cmd = command.CmdStart(
            command_name='test',
            command_target='pkgall',
            inst_storage=storage.InstallationStorage(
                root_dpath=str(tmp_path / 'root')
            ),
        )

        bindir = tmp_path / 'root' / 'bin'
        bindir.mkdir(parents=True)
        mesos_exe = bindir / 'mesos-agent.exe'

        # Installation fails due to non-existing bindir
        with pytest.raises(exceptions.InstallationError) as e:
            cmd.execute()

        # Error message mentions Mesos agent path
        assert str(mesos_exe) in e.value.args[0]
