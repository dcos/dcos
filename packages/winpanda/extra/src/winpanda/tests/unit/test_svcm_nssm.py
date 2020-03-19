import mock
import pytest
import unittest

from svcm import exceptions
from svcm.nssm import WinSvcManagerNSSM

CONF_STUB = {
    'service': {
        'description': 'the_description',
        'displayname': 'the_displayname',
        'name': 'the_name',
        'application': 'the_application',
        'appdirectory': 'the_appdirectory',
        'appparameters': 'the_appparameters',
        'start': 'the_start',
        'dependonservice': 'the_dependonservice',
        'appstdout': 'the_appstdout',
        'appstderr': 'the_appstderr',
        'appenvironmentextra': 'the_appenvironmentextra',
        'appeventsstartpre': 'the_appevents_start_pre',
        'appeventsstartpost': 'the_appevents_start_post',
        'appeventsstoppre': 'the_appevents_stop_pre',
        'appeventsexitpost': 'the_appevents_exit_post',
        'appeventsrotatepre': 'the_appevents_rotate_pre',
        'appeventsrotatepost': 'the_appevents_rotate_post',
        'appeventspowerchange': 'the_appevents_power_change',
        'appeventspowerresume': 'the_appevents_power_resume',
        'appredirecthook': 'the_appredirecthook',
    }
}

RUN_COMMAND_DEFAULT_KWARGS = {
    'check': True,
    'stderr': -1,
    'stdout': -1,
    'timeout': 30,
    'universal_newlines': True
}


def patch_subprocess_run(func):
    def wrapper(*args, **kwargs):
        with mock.patch('svcm.nssm.WinSvcManagerNSSM._verify_executor', return_value='command'):
            with mock.patch('subprocess.run') as mock_subprocess_run:
                kwargs['mock_subprocess'] = mock_subprocess_run
                return func(*args, **kwargs)

    return wrapper


class TestWinSvcManagerNSSM(unittest.TestCase):

    def test_empty_configuration_should_fail(self):
        """No service configuration validation exception."""
        with pytest.raises(exceptions.ServiceConfigError):
            WinSvcManagerNSSM()

    def test_configuration_without_name_should_fail(self):
        """No service configuration name validation exception."""
        conf = {
            'service': {
                'something': ''
            }
        }
        with pytest.raises(exceptions.ServiceConfigError):
            WinSvcManagerNSSM(svc_conf=conf)

    def test_name_only_in_configuration_should_fail(self):
        """No service configuration application name only validation exception."""
        conf = {
            'service': {
                'name': 'test'
            }
        }
        with pytest.raises(exceptions.ServiceConfigError):
            WinSvcManagerNSSM(svc_conf=conf)

    def test_display_name_only_in_configuration_should_fail(self):
        """No service configuration application display name only validation exception."""
        conf = {
            'service': {
                'displayname': 'test'
            }
        }
        with pytest.raises(exceptions.ServiceConfigError):
            WinSvcManagerNSSM(svc_conf=conf)

    def test_parameter_names_should_be_same_as_init(self):
        """Initialize class with all parameters."""
        sm = WinSvcManagerNSSM(svc_conf=CONF_STUB)
        assert sm.svc_name == 'the_displayname'
        assert sm.svc_exec == 'the_application'

        intersection = list(set(sm.svc_pnames_bulk) & set(CONF_STUB['service'].keys()))
        assert len(intersection) == 19

    def test_empty_exec_path_should_fail(self):
        """Setup package with valid but not non executable configuration."""
        sm = WinSvcManagerNSSM(svc_conf=CONF_STUB)
        with pytest.raises(exceptions.ServiceManagerSetupError):
            sm.setup()

    @mock.patch('subprocess.run', side_effect=ValueError)
    @mock.patch('svcm.nssm.WinSvcManagerNSSM._verify_executor')
    def test_subprocess_error_should_fail(self, *args):
        """Setup package with valid but not non executable configuration."""
        sm = WinSvcManagerNSSM(svc_conf=CONF_STUB)
        with pytest.raises(exceptions.ServiceManagerCommandError):
            sm.setup()

    @patch_subprocess_run
    def test_setup_should_exec_18_commands(self, mock_subprocess, *args):
        """Setup valid package."""
        sm = WinSvcManagerNSSM(svc_conf=CONF_STUB)
        sm.setup()
        assert mock_subprocess.call_count == 18

    @patch_subprocess_run
    def test_remove_should_run_remove_command(self, mock_subprocess, *args):
        """Remove valid package."""
        sm = WinSvcManagerNSSM(svc_conf=CONF_STUB)
        sm.remove()
        cmd = 'command remove the_displayname confirm'
        mock_subprocess.assert_called_once_with(cmd, **RUN_COMMAND_DEFAULT_KWARGS)

    @patch_subprocess_run
    def test_enable_should_set_auto_start(self, mock_subprocess, *args):
        """Enable valid package."""
        sm = WinSvcManagerNSSM(svc_conf=CONF_STUB)
        sm.enable()
        cmd = 'command set the_displayname start SERVICE_AUTO_START'
        mock_subprocess.assert_called_once_with(cmd, **RUN_COMMAND_DEFAULT_KWARGS)

    @patch_subprocess_run
    def test_disable_should_set_service_demand_start(self, mock_subprocess, *args):
        """Disable valid package."""
        sm = WinSvcManagerNSSM(svc_conf=CONF_STUB)
        sm.disable()
        cmd = 'command set the_displayname start SERVICE_DEMAND_START'
        mock_subprocess.assert_called_once_with(cmd, **RUN_COMMAND_DEFAULT_KWARGS)

    @patch_subprocess_run
    def test_start_should_run_start(self, mock_subprocess, *args):
        """Start valid package."""
        sm = WinSvcManagerNSSM(svc_conf=CONF_STUB)
        sm.start()
        cmd = 'command start the_displayname'
        mock_subprocess.assert_called_once_with(cmd, **RUN_COMMAND_DEFAULT_KWARGS)

    @patch_subprocess_run
    def test_stop_should_run_stop(self, mock_subprocess, *args):
        """Stop valid package."""
        sm = WinSvcManagerNSSM(svc_conf=CONF_STUB)
        sm.stop()
        cmd = 'command stop the_displayname'
        mock_subprocess.assert_called_once_with(cmd, **RUN_COMMAND_DEFAULT_KWARGS)

    @patch_subprocess_run
    def test_restart_should_run_restart(self, mock_subprocess, *args):
        """Restart valid package."""
        sm = WinSvcManagerNSSM(svc_conf=CONF_STUB)
        sm.restart()
        cmd = 'command restart the_displayname'
        mock_subprocess.assert_called_once_with(cmd, **RUN_COMMAND_DEFAULT_KWARGS)

    @patch_subprocess_run
    def test_status_should_run_status(self, mock_subprocess, *args):
        """Get valid package status."""
        sm = WinSvcManagerNSSM(svc_conf=CONF_STUB)
        sm.status()
        cmd = 'command status the_displayname'
        mock_subprocess.assert_called_once_with(cmd, **RUN_COMMAND_DEFAULT_KWARGS)
