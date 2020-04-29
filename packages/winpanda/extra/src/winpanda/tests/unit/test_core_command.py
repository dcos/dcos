import mock
import unittest

from core.command import CmdUpgrade
from core import command


def mock_upgrade_handle(func):
    def wrapper(*args, **kwargs):
        with mock.patch.object(CmdUpgrade, '__init__', mock.Mock(return_value=None)):
            with mock.patch.object(CmdUpgrade, '_handle_upgrade_pre'):
                with mock.patch.object(CmdUpgrade, '_handle_teardown'):
                    with mock.patch.object(CmdUpgrade, '_handle_teardown_post'):
                        with mock.patch.object(CmdUpgrade, '_handle_clean_setup'):
                            with mock.patch('core.command.CmdUpgrade.state'):
                                func(*args, **kwargs)
    return wrapper


def mock_rollback_handle(func):
    def wrapper(*args, **kwargs):
        with mock.patch.object(CmdUpgrade, '_rollback_upgrade_pre'):
            with mock.patch.object(CmdUpgrade, '_rollback_teardown'):
                with mock.patch.object(CmdUpgrade, '_rollback_teardown_post'):
                    with mock.patch.object(CmdUpgrade, '_rollback_clean_setup'):
                        func(*args, **kwargs)
    return wrapper


class TestCmdUpgradeRobustness(unittest.TestCase):

    @mock.patch.object(CmdUpgrade, '__init__', mock.Mock(return_value=None))
    def test_all_upgrade_actions_should_have_compensation(self):
        cmd = CmdUpgrade()
        assert command.STEPS_UPGRADE.keys() == command.STEPS_ROLLBACK_UPGRADE.keys()

    @mock_upgrade_handle
    @mock.patch('core.command.CmdUpgrade._current_state', new=mock.PropertyMock(
        return_value=None))
    def test_init_state_calls_order_should_be_correct(self):
        """Check upgrade command execution steps order."""
        cmd = CmdUpgrade()
        cmd.msg_src = cmd.__class__.__name__

        cmd.execute()

        expected_calls = [mock.call(i) for i in (
            command.STEP_UPGRADE_TEARDOWN,
            command.STEP_UPGRADE_TEARDOWN_POST,
            command.STEP_UPGRADE,
            command.STATE_NEEDS_START)]

        cmd.state.set_state.assert_has_calls(expected_calls, any_order=False)

    @mock_upgrade_handle
    @mock.patch('core.command.CmdUpgrade._current_state', new=mock.PropertyMock(
        return_value=command.STEP_UPGRADE_TEARDOWN))
    def test_teardown_state_calls_order_should_be_correct(self):
        """Check upgrade command execution steps order."""
        cmd = CmdUpgrade()
        cmd.msg_src = cmd.__class__.__name__

        cmd.execute()

        expected_calls = [mock.call(i) for i in (
            command.STEP_UPGRADE,
            command.STATE_NEEDS_START)]

        cmd.state.set_state.assert_has_calls(expected_calls, any_order=False)
        cmd.state._handle_upgrade_pre.assert_not_called()

    @mock_upgrade_handle
    @mock_rollback_handle
    @mock.patch('core.command.CmdUpgrade._current_state', new=mock.PropertyMock(
        side_effect=[None, command.STEP_UPGRADE]))  # mock calls for handle and rollback
    def test_rollback_calls_order_should_be_correct(self):
        cmd = CmdUpgrade()
        cmd.msg_src = cmd.__class__.__name__
        cmd._handle_clean_setup.side_effect = mock.Mock(side_effect=Exception())

        cmd.execute()

        # check rollback execution result
        cmd.state.unset_state.assert_called_once()

        # check rollback execution during upgrade exception
        cmd._rollback_clean_setup.assert_called_once()
        cmd._rollback_teardown_post.assert_called_once()
        cmd._rollback_teardown.assert_called_once()
        cmd._rollback_upgrade_pre.assert_called_once()

        # check rollback steps execution order
        expected_calls = [mock.call(i) for i in (
            # upgrading flow
            command.STEP_PRE_UPGRADE,
            command.STEP_UPGRADE_TEARDOWN,
            command.STEP_UPGRADE_TEARDOWN_POST,
            command.STEP_UPGRADE,
            # rollback flow
            command.STEP_UPGRADE_TEARDOWN_POST,
            command.STEP_UPGRADE_TEARDOWN,
            command.STEP_PRE_UPGRADE)]

        cmd.state.set_state.assert_has_calls(expected_calls, any_order=False)
