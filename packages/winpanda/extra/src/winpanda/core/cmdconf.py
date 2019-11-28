"""Panda package management for Windows.

Command configuration object definitions.
"""
import abc
from pathlib import Path
import posixpath

from common import constants as cm_const
from common import logger
from common.cli import CLI_COMMAND, CLI_CMDOPT, CLI_CMDTARGET
from common.storage import InstallationStorage, ISTOR_NODE
from core import exceptions as cr_exc
from core.rc_ctx import ResourceContext
from core import utils as cr_utl

from common import utils as cm_utl


LOG = logger.get_logger(__name__)

CMDCONF_TYPES = {}


def create(**cmd_opts):
    """Create configuration for a command.

    :param cmd_opts: dict, command options:
                     {
                         'command_name': <str>,

                     }
    """
    command_name = cmd_opts.get(CLI_CMDOPT.CMD_NAME, '')

    return CMDCONF_TYPES[command_name](**cmd_opts)


def cmdconf_type(command_name):
    """Register a command configuration class in the config types registry.

    :param command_name: str, name of a command
    """
    def decorator(cls):
        """"""
        CMDCONF_TYPES[command_name] = cls
        return cls

    return decorator


class CommandConfig(metaclass=abc.ABCMeta):
    """Abstract base class for command configuration types.
    """
    def __init__(self, **cmd_opts):
        """Constructor."""
        self.cmd_opts = cmd_opts

    def __repr__(self):
        return (
            '<%s(cmd_opts="%s")>' % (self.__class__.__name__, self.cmd_opts)
        )

    def __str__(self):
        return self.__repr__()


@cmdconf_type(CLI_COMMAND.SETUP)
class CmdConfigSetup(CommandConfig):
    """Configuration for the 'setup' command."""
    def __init__(self, **cmd_opts):
        """"""
        self.msg_src = self.__class__.__name__
        super(CmdConfigSetup, self).__init__(**cmd_opts)
        # DC/OS installation storage manager
        self.inst_storage = InstallationStorage(
            root_dpath=cmd_opts.get(CLI_CMDOPT.INST_ROOT),
            cfg_dpath=cmd_opts.get(CLI_CMDOPT.INST_CONF),
            pkgrepo_dpath=cmd_opts.get(CLI_CMDOPT.INST_PKGREPO),
            state_dpath=cmd_opts.get(CLI_CMDOPT.INST_STATE),
            var_dpath=cmd_opts.get(CLI_CMDOPT.INST_VAR),
        )
        LOG.debug(f'{self.msg_src}: istor_nodes:'
                  f' {self.inst_storage.istor_nodes}')
        if cmd_opts.get(CLI_CMDOPT.CMD_TARGET) == CLI_CMDTARGET.PKGALL:
            # Make sure that the installation storage is in consistent state
            self.inst_storage.construct()

        # DC/OS cluster setup parameters
        self.cluster_conf_nop = False
        self.cluster_conf = self.get_cluster_conf()
        LOG.debug(f'{self.msg_src}: cluster_conf: {self.cluster_conf}')

        # Reference list of DC/OS packages
        self.ref_pkg_list = self.get_ref_pkg_list()
        LOG.debug(f'{self.msg_src}: ref_pkg_list: {self.ref_pkg_list}')

        # DC/OS aggregated configuration object
        self.dcos_conf = self.get_dcos_conf()
        LOG.debug(f'{self.msg_src}: dcos_conf: {self.dcos_conf}')

    def get_cluster_conf(self):
        """"Get a collection of DC/OS cluster configuration options.

        :return: dict, configparser.ConfigParser.read_dict() compatible data
        """
        # Load cluster configuration file
        fpath = Path(self.cmd_opts.get(CLI_CMDOPT.DCOS_CLUSTERCFGPATH))

        # Unblock irrelevant local operations
        if str(fpath) == 'NOP':
            self.cluster_conf_nop = True
            LOG.info(f'{self.msg_src}: cluster_conf: NOP')
            return {}

        if not fpath.is_absolute():
            if self.inst_storage.cfg_dpath.exists():
                fpath = self.inst_storage.cfg_dpath.joinpath(fpath)
            else:
                fpath = Path('.').resolve().joinpath(fpath)

        cluster_conf = cr_utl.rc_load_ini(
            fpath, emheading='Cluster setup descriptor'
        )

        # CLI options take precedence, if any.
        # list(tuple('ipaddr', 'port'))
        cli_master_priv_ipaddrs = [
            ipaddr.partition(':')[::2] for ipaddr in
            self.cmd_opts.get(CLI_CMDOPT.MASTER_PRIVIPADDR, '').split(' ') if
            ipaddr != ''
        ]
        mnode_sects = [
            sect for sect in cluster_conf if sect.startswith('master-node')
        ]
        # iterator(tuple('ipaddr', 'port'), str)
        change_map = zip(cli_master_priv_ipaddrs, mnode_sects)
        for item in change_map:
            if item[0][0]:
                cluster_conf[item[1]]['privateipaddr'] = item[0][0]
                if item[0][1]:
                    try:
                        port = int(item[0][1])
                    except (ValueError, TypeError):
                        port = cm_const.ZK_CLIENTPORT_DFT
                    port = (port if 0 < port < 65536 else
                            cm_const.ZK_CLIENTPORT_DFT)
                    cluster_conf[item[1]]['zookeeperclientport'] = port

        # Add extra 'master-node' sections, if CLI provides extra arguments
        extra_cli_items = cli_master_priv_ipaddrs[len(mnode_sects):]
        for n, item in enumerate(extra_cli_items):
            if item[0]:
                # TODO: Implement collision tolerance for section names.
                cluster_conf[f'master-node-extra{n}'] = {}
                cluster_conf[f'master-node-extra{n}']['privateipaddr'] = (
                    item[0]
                )
                if item[1]:
                    try:
                        port = int(item[1])
                    except (ValueError, TypeError):
                        port = cm_const.ZK_CLIENTPORT_DFT
                    port = (port if 0 < port < 65536 else
                            cm_const.ZK_CLIENTPORT_DFT)
                    cluster_conf[f'master-node-extra{n}'][
                        'zookeeperclientport'
                    ] = port
        # DC/OS storage distribution parameters
        cli_dstor_url = self.cmd_opts.get(CLI_CMDOPT.DSTOR_URL)
        cli_dstor_pkgrepo_path = self.cmd_opts.get(
            CLI_CMDOPT.DSTOR_PKGREPOPATH
        )
        cli_dstor_pkglist_path = self.cmd_opts.get(
            CLI_CMDOPT.DSTOR_PKGLISTPATH
        )
        cli_dstor_dcoscfg_path = self.cmd_opts.get(
            CLI_CMDOPT.DSTOR_DCOSCFGPATH
        )
        if not cluster_conf.get('distribution-storage'):
            cluster_conf['distribution-storage'] = {}

        if cli_dstor_url:
            cluster_conf['distribution-storage']['rooturl'] = cli_dstor_url
        if cli_dstor_pkgrepo_path:
            cluster_conf['distribution-storage']['pkgrepopath'] = (
                cli_dstor_pkgrepo_path
            )
        if cli_dstor_pkglist_path:
            cluster_conf['distribution-storage']['pkglistpath'] = (
                cli_dstor_pkglist_path
            )
        if cli_dstor_dcoscfg_path:
            cluster_conf['distribution-storage']['dcoscfgpath'] = (
                cli_dstor_dcoscfg_path
            )

        # Local parameters of DC/OS node
        cli_local_priv_ipaddr = self.cmd_opts.get(CLI_CMDOPT.LOCAL_PRIVIPADDR)
        if not cluster_conf.get('local'):
            cluster_conf['local'] = {}

        if cli_local_priv_ipaddr:
            cluster_conf['local']['privateipaddr'] = cli_local_priv_ipaddr

        return cluster_conf

    def get_ref_pkg_list(self):
        """Get the current reference package list.

        :return: list, JSON-formatted data
        """
        dstor_root_url = (
            self.cluster_conf.get('distribution-storage', {}).get(
                'rooturl', ''
            )
        )
        dstor_pkglist_path = (
            self.cluster_conf.get('distribution-storage', {}).get(
                'pkglistpath', ''
            )
        )
        # Unblock irrelevant local operations
        if self.cluster_conf_nop or dstor_pkglist_path == 'NOP':
            LOG.info(f'{self.msg_src}: ref_pkg_list: NOP')
            return []

        rpl_url = posixpath.join(dstor_root_url, dstor_pkglist_path)
        rpl_fname = Path(dstor_pkglist_path).name

        try:
            cm_utl.download(rpl_url, str(self.inst_storage.tmp_dpath))
            LOG.debug(f'{self.msg_src}: Reference package list: Download:'
                      f' {rpl_fname}: {rpl_url}')
        except Exception as e:
            raise cr_exc.RCDownloadError(
                f'Reference package list: Download: {rpl_fname}: {rpl_url}:'
                f' {type(e).__name__}: {e}'
            ) from e

        rpl_fpath = self.inst_storage.tmp_dpath.joinpath(rpl_fname)
        try:
            return cr_utl.rc_load_json(
                rpl_fpath, emheading=f'Reference package list: {rpl_fname}'
            )
        except cr_exc.RCError as e:
            raise e
        finally:
            rpl_fpath.unlink()

    def get_dcos_conf(self):
        """Get the DC/OS aggregated configuration object.

        :return: dict, set of DC/OS shared and package specific configuration
                 objects:
                     {
                         'package': {[
                             {'path': <str>, 'content': <str>},
                             ...
                         ]}
                     }
        """

        dstor_root_url = (
            self.cluster_conf.get('distribution-storage', {}).get(
                'rooturl', ''
            )
        )
        dstor_dcoscfg_path = (
            self.cluster_conf.get('distribution-storage', {}).get(
                'dcoscfgpath', ''
            )
        )
        # Unblock irrelevant local operations
        if self.cluster_conf_nop or dstor_dcoscfg_path == 'NOP':
            LOG.info(f'{self.msg_src}: dcos_conf: NOP')
            return {}

        dcoscfg_url = posixpath.join(dstor_root_url, dstor_dcoscfg_path)
        dcoscfg_fname = Path(dstor_dcoscfg_path).name

        try:
            cm_utl.download(dcoscfg_url, str(self.inst_storage.tmp_dpath))
            LOG.debug(f'{self.msg_src}: DC/OS aggregated config: Download:'
                      f' {dcoscfg_fname}: {dcoscfg_url}')
        except Exception as e:
            raise cr_exc.RCDownloadError(
                f'DC/OS aggregated config: Download: {dcoscfg_fname}:'
                f' {dcoscfg_url}: {type(e).__name__}: {e}'
            ) from e

        dcoscfg_fpath = self.inst_storage.tmp_dpath.joinpath(dcoscfg_fname)

        try:
            dcos_conf = cr_utl.rc_load_yaml(
                dcoscfg_fpath,
                emheading=f'DC/OS aggregated config: {dcoscfg_fname}',
                render=True,
                context=ResourceContext(
                    istor_nodes=self.inst_storage.istor_nodes,
                    cluster_conf=self.cluster_conf
                )
            )

            if (not isinstance(dcos_conf, dict) or not
                    isinstance(dcos_conf.get('package'), list)):
                raise cr_exc.RCInvalidError(
                    f'DC/OS aggregated config: {dcos_conf}'
                )

            for element in dcos_conf.get('package'):
                if (not isinstance(element, dict) or not
                        isinstance(element.get('path'), str) or not
                        isinstance(element.get('content'), str)):
                    raise cr_exc.RCElementError(
                        f'DC/OS aggregated config: {element}'
                    )

            return dcos_conf

        except cr_exc.RCError as e:
            raise e
        finally:
            dcoscfg_fpath.unlink()


@cmdconf_type(CLI_COMMAND.START)
class CmdConfigStart(CommandConfig):
    """Configuration for the 'start' command."""
    def __init__(self, **cmd_opts):
        """"""
        super(CmdConfigStart, self).__init__(**cmd_opts)
        # Create DC/OS installation storage manager
        self.inst_storage = InstallationStorage(
            root_dpath=cmd_opts.get(CLI_CMDOPT.INST_ROOT),
            cfg_dpath=cmd_opts.get(CLI_CMDOPT.INST_CONF),
            pkgrepo_dpath=cmd_opts.get(CLI_CMDOPT.INST_PKGREPO),
            state_dpath=cmd_opts.get(CLI_CMDOPT.INST_STATE),
            var_dpath=cmd_opts.get(CLI_CMDOPT.INST_VAR)
        )
        LOG.debug(f'{self.__class__.__name__}: inst_storage: istor_nodes:'
                  f' {self.inst_storage.istor_nodes}')
        # Make sure that the installation storage is in consistent state
        self.inst_storage.construct()

        # DC/OS cluster setup parameters
        self.cluster_conf = {}
        LOG.debug(
            f'{self.__class__.__name__}: cluster_conf: {self.cluster_conf}'
        )
