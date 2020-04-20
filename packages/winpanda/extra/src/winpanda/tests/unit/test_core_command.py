import mock
import unittest

from core.command import CmdUpgrade
from core import command, cmdconf


def mock_upgrade_handle(func):
    def wrapper(*args, **kwargs):
        with mock.patch.object(CmdUpgrade, '__init__', mock.Mock(return_value=None)):
            with mock.patch.object(CmdUpgrade, '_check_mesos_agent'):
                with mock.patch.object(CmdUpgrade, '_handle_upgrade_pre'):
                    with mock.patch.object(CmdUpgrade, '_handle_teardown'):
                        with mock.patch.object(CmdUpgrade, '_handle_teardown_post'):
                            with mock.patch.object(CmdUpgrade, '_handle_clean_setup'):
                                func(*args, **kwargs)
    return wrapper


class TestCmdUpgradeRobustness(unittest.TestCase):

    @mock_upgrade_handle
    def test_init_state_calls_order_should_be_correct(self):
        """Check upgrade command execution steps order."""
        cmd = CmdUpgrade()
        cmd.msg_src = cmd.__class__.__name__

        cmd.state = mock.Mock()
        cmd.state.get_state.return_value = None

        cmd.execute()

        expected_calls = [mock.call(i) for i in (
            command.STEP_UPGRADE_TEARDOWN,
            command.STEP_UPGRADE,
            command.STEP_START_AFTER_UPGRADE,
            command.STATE_NEEDS_START)]

        cmd.state.set_state.assert_has_calls(expected_calls, any_order=False)

    @mock_upgrade_handle
    def test_teardown_state_calls_order_should_be_correct(self):
        """Check upgrade command execution steps order."""
        cmd = CmdUpgrade()
        cmd.msg_src = cmd.__class__.__name__

        cmd.state = mock.Mock()
        cmd.state.get_state.return_value = command.STEP_UPGRADE_TEARDOWN

        cmd.execute()

        expected_calls = [mock.call(i) for i in (
            command.STEP_UPGRADE,
            command.STEP_START_AFTER_UPGRADE,
            command.STATE_NEEDS_START)]

        cmd.state.set_state.assert_has_calls(expected_calls, any_order=False)
        cmd.state._handle_upgrade_pre.assert_not_called()

    @mock_upgrade_handle
    def test_rollback_calls_order_should_be_correct(self):
        cmd = CmdUpgrade()
        cmd.msg_src = cmd.__class__.__name__

        cmd.state = mock.Mock()
        cmd.state.get_state.side_effect = [None, command.STATE_NEEDS_START]
        cmd._handle_upgrade_pre.side_effect = mock.Mock(side_effect=Exception('Dumy'))

        cmd.execute()

        expected_calls = [mock.call(i) for i in (
            command.STEP_UPGRADE,
            command.STEP_UPGRADE_TEARDOWN)]

        cmd.state.set_state.assert_has_calls(expected_calls, any_order=False)
        cmd.state.unset_state.assert_called_once()
