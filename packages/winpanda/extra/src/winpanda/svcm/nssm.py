"""Panda package management for Windows.

Windows service management: NSSM-based service manager definition.

Ref:
  [1] NSSM - the Non-Sucking Service Manager
      https://nssm.cc/description
  [2] nssm/README.txt
      https://git.nssm.cc/nssm/nssm/src/master/README.txt
"""
import configparser as cfp
import enum
import os
from pathlib import Path
import re
import subprocess

from . import base
from . import exceptions as svcm_exc
from common import exceptions as cm_exc
from common import logger
from common import utils as cm_utl


LOG = logger.get_logger(__name__)


class NSSMParameter(enum.Enum):
    """NSSM parameter set."""
    DESCRIPTION = 'description'
    DISPLAYNAME = 'displayname'
    NAME = 'name'
    APPLICATION = 'application'
    APPDIRECTORY = 'appdirectory'
    APPPARAMETERS = 'appparameters'
    START = 'start'
    DEPENDONSERVICE = 'dependonservice'
    APPSTDOUT = 'appstdout'
    APPSTDERR = 'appstderr'
    APPENVIRONMENT = 'appenvironment'
    APPENVIRONMENTEXTRA = 'appenvironmentextra'
    APPEVENTSSTARTPRE = 'appevents start/pre'
    APPEVENTSSTARTPOST = 'appevents start/post'
    APPEVENTSSTOPPRE = 'appevents stop/pre'
    APPEVENTSEXITPOST = 'appevents exit/post'
    APPEVENTSROTATEPRE = 'appevents rotate/pre'
    APPEVENTSROTATEPOST = 'appevents rotate/post'
    APPEVENTSPOWERCHANGE = 'appevents power/change'
    APPEVENTSPOWERRESUME = 'appevents power/resume'
    APPREDIRECTHOOK = 'appredirecthook'

    @classmethod
    def names(cls):
        return [k.lower() for k in cls.__members__.keys()]

    @classmethod
    def names_required(cls):
        return ['displayname', 'application']


class NSSMCommand(enum.Enum):
    """NSSM command set."""
    INSTALL = 'install'
    REMOVE = 'remove'
    START = 'start'
    STOP = 'stop'
    RESTART = 'restart'
    STATUS = 'status'
    SET = 'set'

    @classmethod
    def values(cls):
        return [m.value for m in cls.__members__.values()]

    @classmethod
    def values_primitive(cls):
        # Names of primitive commands.
        names_primitive = ('START', 'STOP', 'RESTART', 'STATUS')
        return [
            m.value for n, m in cls.__members__.items() if n in names_primitive
        ]


class NSSMConfSection(enum.Enum):
    """NSSM configuration file sections."""
    SERVICE = 'service'


class SVC_STATUS:
    """System service status."""
    STOPPED = 'SERVICE_STOPPED'
    START_PENDING = 'SERVICE_START_PENDING'
    RUNNING = 'SERVICE_RUNNING'
    PAUSED = 'SERVICE_PAUSED'


VALID_SVC_STATUSES = [getattr(SVC_STATUS, sname) for sname in
                      SVC_STATUS.__dict__ if not sname.startswith('__')]


def _verify_svcm_executor(command):
    """Discover/verify service manager executor instance.

    :param command: callable, a method of the service manager that should be
                    preceded by the discovery/verification procedure
    :return:
    """
    def decorator(manager, *args, **kwargs):
        """

        :param manager: WindowsServiceManager, system service manager object
        :param args:    tuple, positional arguments to a service management
                        command
        :param kwargs:  dict, keyword arguments to a service management command
        :return:        object, result of a method being decorated
        """
        if manager.exec_path is None:
            manager.exec_path = manager._verify_executor()

        return command(manager, *args, **kwargs)

    return decorator


@base.svcm_type('nssm')
class WinSvcManagerNSSM(base.WindowsServiceManager):
    """NSSM-based Windows service manager."""
    _exec_fname = 'nssm.exe'  # Executable file name.
    _exec_id_pattern = re.compile(r'^NSSM.*$')  # Executable identity.
    _ws = re.compile(r'[\s]+')

    def __init__(self, **svcm_opts):
        """Constructor."""
        super(WinSvcManagerNSSM, self).__init__(**svcm_opts)
        _svc_conf = svcm_opts.get('svc_conf', {})

        self.msg_src = self.__class__.__name__

        assert isinstance(_svc_conf, dict), (
            f'{self.msg_src}: Argument: svc_conf:'
            f' Got {type(self.svc_conf).__name__} instead of dict'
        )

        self.svc_conf = cfp.ConfigParser()
        self.svc_conf.read_dict(_svc_conf)

        self.exec_path = None  # System service manager executable path

        self.svc_name = None
        self.svc_exec = None
        self.svc_pnames_bulk = None

        self.verify_svcm_options()

    def __str__(self):
        return str({
            'svc_conf': {k: dict(v) for k, v in self.svc_conf.items()},
            'exec_path': str(self.exec_path),
            'svc_name': self.svc_name,
            'svc_exec': self.svc_exec,
            'svc_pnames_bulk': self.svc_pnames_bulk,
        })

    def verify_svcm_options(self):
        """Verify/refine Windows service manager options."""
        self._verify_svc_conf()

    def _verify_executor(self):
        """Check service management executor tool."""
        exec_path = self.svcm_opts.get('exec_path')
        exec_path = (exec_path if isinstance(exec_path, Path) else
                     Path(self._exec_fname))

        if not exec_path.is_absolute():
            # Look up in the system's PATH
            for p in os.environ.get('PATH').split(';'):
                abs_p = Path(p).joinpath(exec_path)
                if abs_p.is_file():
                    exec_path = abs_p
                    break
            else:
                raise svcm_exc.ServiceManagerSetupError(
                    f'Executable not found: {exec_path}'
                )

        if not exec_path.is_file():
            raise svcm_exc.ServiceManagerSetupError(
                f'Executable not found: {exec_path}'
            )

        # Check if the provided executable can be run
        try:
            subproc_run = subprocess.run(
                [f'{exec_path}', 'version'], stdout=subprocess.PIPE,
                timeout=5, check=True, universal_newlines=True
            )
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            raise svcm_exc.ServiceManagerSetupError(
                f'Executable broken: {exec_path}: {type(e).__name__}: {e}'
            )
        # Verify the identity of provided executable
        if self._exec_id_pattern.search(
                subproc_run.stdout.splitlines()[0]
        ) is None:
            raise svcm_exc.ServiceManagerSetupError(
                f'Executable mismatch: {exec_path}'
            )

        return exec_path

    def _verify_svc_conf(self):
        """Check service configuration"""
        if not self.svc_conf.has_section(NSSMConfSection.SERVICE.value):
            raise svcm_exc.ServiceConfigError(
                f'Section not found: {NSSMConfSection.SERVICE.value}'

            )

        self.svc_pnames_bulk = self.svc_conf.options(
            NSSMConfSection.SERVICE.value
        )

        if NSSMParameter.DISPLAYNAME.name.lower() in self.svc_pnames_bulk:
            self.svc_name = self.svc_conf.get(
                NSSMConfSection.SERVICE.value,
                NSSMParameter.DISPLAYNAME.name.lower()
            )
            if NSSMParameter.NAME.name.lower() in self.svc_pnames_bulk:
                self.svc_conf.remove_option(NSSMConfSection.SERVICE.value,
                                            NSSMParameter.NAME.name.lower())
                self.svc_pnames_bulk = self.svc_conf.options(
                    NSSMConfSection.SERVICE.value
                )
        elif NSSMParameter.NAME.name.lower() in self.svc_pnames_bulk:
            self.svc_name = self.svc_conf.get(NSSMConfSection.SERVICE.value,
                                              NSSMParameter.NAME.name.lower())
        else:
            raise svcm_exc.ServiceConfigError(
                f'Required parameter unavailable:'
                f' {NSSMParameter.DISPLAYNAME.name.lower()}/'
                f'{NSSMParameter.NAME.name.lower()}'
            )

        if NSSMParameter.APPLICATION.name.lower() in self.svc_pnames_bulk:
            self.svc_exec = self.svc_conf.get(
                NSSMConfSection.SERVICE.value,
                NSSMParameter.APPLICATION.name.lower()
            )
        else:
            raise svcm_exc.ServiceConfigError(
                f'Required parameter unavailable:'
                f' {NSSMParameter.APPLICATION.name.lower()}'
            )

    def _get_svc_setup_pchain(self):
        """"Get an ordered collection of CLI parameters to be passed to the
        underlying service management utility (executor) when performing the
        'setup' command.

        :return: list[(nssm_cmd, list[cli_param])], set of params for service
                 setup call chain:

                 install <servicename> <program>

                 set <servicename> <parameter1> <value1>
                 set <servicename> <parameter2> <value2>
                 ...
                 set <servicename> <parameterN> <valueN>
        """
        setup_pchain = []

        pnames_valid = NSSMParameter.names()
        pnames_required = NSSMParameter.names_required()

        # Parameters for nssm 'install' command.
        cmd = NSSMCommand.INSTALL.value
        cmd_plist = [self.svc_name, self.svc_exec]
        setup_pchain.append((cmd, cmd_plist))
        # Optional parameters to be set by nssm 'set' command.
        pnames_opt = [
            pname for pname in self.svc_pnames_bulk if (
                pname in pnames_valid and pname not in pnames_required
            )
        ]
        cmd = NSSMCommand.SET.value

        for pname in pnames_opt:
            pname_cl_form = NSSMParameter[pname.upper()].value
            pval = self.svc_conf.get(NSSMConfSection.SERVICE.value, pname)
            if self._ws.search(pval):
                err_msg = (
                    f'ServiceConfig: {self.svc_name}: Parameter value'
                    f' string possibly requires quotation:'
                    f' section[{NSSMConfSection.SERVICE.value}]'
                    f' parameter[{pname}] value[{pval}]'
                )
                LOG.warning(err_msg)
            cmd_plist = [self.svc_name] + pname_cl_form.split() + [pval]
            setup_pchain.append((cmd, cmd_plist))

        return setup_pchain

    def _run_external_command(self, svcm_op_name, cl_elements):
        """Run an external command within the scope of a service manager's
        operation of a higher level.

        :param svcm_op_name: str, name of a service manager operation which
                             this external command is a part of
        :param cl_elements:  list[str], a sequence of individual elements of
                             command line, beginning with executable name
        """
        assert isinstance(cl_elements, list), (
            f'{self.msg_src}: Argument: cl_elements:'
            f' Got {type(cl_elements).__name__} instead of list'
        )

        cmd_line = ' '.join(cl_elements)
        try:
            ext_cmd_run = cm_utl.run_external_command(cmd_line)
            LOG.debug(f'{self.msg_src}: {svcm_op_name.capitalize()}:'
                      f' {cmd_line}: OK')
        except cm_exc.ExternalCommandError as e:
            LOG.debug(f'{self.msg_src}: {svcm_op_name.capitalize()}:'
                      f' {cmd_line}: {type(e).__name__}: {e}')
            raise svcm_exc.ServiceManagerCommandError(
                f'{svcm_op_name.capitalize()}: {e}'
            ) from e

        return ext_cmd_run

    @_verify_svcm_executor
    def setup(self):
        """Setup (register) configuration for a Windows service.
        """
        svc_setup_pchain = self._get_svc_setup_pchain()

        for call_params in svc_setup_pchain:
            cl_elements = [f'{self.exec_path}', call_params[0]]
            required_pcount = (
                2 if call_params[0] == NSSMCommand.INSTALL.value else 3
            )

            if len(call_params[1]) < required_pcount:
                raise svcm_exc.ServiceManagerCommandError(
                    f'Insufficient arguments: '
                    f'{cl_elements.extend(call_params[1])}'
                )

            cl_elements.extend(call_params[1])

            self._run_external_command('setup', cl_elements)

        # TODO: Add a cleanup procedure for the case of unsuccessful service
        #       setup operation.

    @_verify_svcm_executor
    def remove(self):
        """Remove configuration for a Windows service."""
        cl_elements = [
            f'{self.exec_path}', NSSMCommand.REMOVE.value,
            self.svc_name, 'confirm'
        ]

        self._run_external_command('remove', cl_elements)

    @_verify_svcm_executor
    def enable(self):
        """Turn service's  auto-start flag on (start service at OS bootstrap).
        """
        cl_elements = [
            f'{self.exec_path}', NSSMCommand.SET.value,
            self.svc_name, NSSMParameter.START.value, 'SERVICE_AUTO_START'
        ]

        self._run_external_command('enable', cl_elements)

    @_verify_svcm_executor
    def disable(self):
        """Turn service's  auto-start flag off (do not start service at OS
        bootstrap).
        """
        cl_elements = [
            f'{self.exec_path}', NSSMCommand.SET.value,
            self.svc_name, NSSMParameter.START.value, 'SERVICE_DEMAND_START'
        ]

        self._run_external_command('disable', cl_elements)

    @_verify_svcm_executor
    def _primitive_command(self, command_name):
        """Primitive command template."""
        assert command_name in NSSMCommand.values_primitive(), (
            f'{self.msg_src}: Non primitive command: {command_name}'
        )

        cl_elements = [f'{self.exec_path}', command_name, self.svc_name]

        return self._run_external_command(command_name, cl_elements)

    def start(self):
        """Start a registered service (immediately)."""
        self._primitive_command(NSSMCommand.START.value)

    def stop(self):
        """Stop a registered service (immediately)."""
        self._primitive_command(NSSMCommand.STOP.value)

    def restart(self):
        """Restart a registered service (immediately)."""
        self._primitive_command(NSSMCommand.RESTART.value)

    def status(self):
        """Discover status of a registered service.
        """
        cmd_run = self._primitive_command(NSSMCommand.STATUS.value)

        return cmd_run.returncode, cmd_run.stdout, cmd_run.stderr
