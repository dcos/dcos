"""Panda package management for Windows.

Command configuration object definitions.
"""
import abc
from pathlib import Path
import posixpath
import tempfile as tf

from common import constants as cm_const
from common import logger
from common import utils as cm_utl
from common.cli import CLI_COMMAND, CLI_CMDOPT, CLI_CMDTARGET
from common.storage import InstallationStorage
from core import exceptions as cr_exc
from core import template
from core import utils as cr_utl


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


def cmdconf_type(command_name: str):
    """Register a command configuration class in the config types registry.

    :param command_name: str, name of a command
    """
    def decorator(cls):
        """"""
        CMDCONF_TYPES[command_name] = cls
        return cls

    return decorator


class CommandConfig(metaclass=abc.ABCMeta):
    """Abstract base class for command configuration types."""

    def __init__(self, **cmd_opts):
        """Constructor."""
        self.msg_src = self.__class__.__name__
        self.cmd_opts = cmd_opts

        # DC/OS installation storage manager
        self.inst_storage = InstallationStorage(
            root_dpath=self.cmd_opts.get(CLI_CMDOPT.INST_ROOT),
            cfg_dpath=self.cmd_opts.get(CLI_CMDOPT.INST_CONF),
            pkgrepo_dpath=self.cmd_opts.get(CLI_CMDOPT.INST_PKGREPO),
            state_dpath=self.cmd_opts.get(CLI_CMDOPT.INST_STATE),
            var_dpath=self.cmd_opts.get(CLI_CMDOPT.INST_VAR),
        )
        LOG.debug(f'{self.msg_src}: istor_nodes:'
                  f' {self.inst_storage.istor_nodes}')

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
        super(CmdConfigSetup, self).__init__(**cmd_opts)

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

    def get_cluster_conf(self):
        """"Get a collection of DC/OS cluster configuration options.

        :return: dict, configparser.ConfigParser.read_dict() compatible data
        """
        # TODO: Functionality implemented in this method needs to be reused
        #       in other application parts (e.g. CmdConfigUpgrade) and so, it
        #       has been arranged as a standalone function get_cluster_conf().
        #       Thus the CmdConfigSetup is to be moved to use that standalone
        #       function instead of this method to avoid massive code
        #       duplication.

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
        # TODO: Functionality implemented in this method needs to be reused
        #       in other application parts (e.g. CmdConfigUpgrade) and so, it
        #       has been arranged as a standalone function get_ref_pkg_list().
        #       Thus the CmdConfigSetup is to be moved to use that standalone
        #       function instead of this method to avoid massive code
        #       duplication.
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
        try:
            rpl_fpath = cm_utl.download(rpl_url, self.inst_storage.tmp_dpath)
            LOG.debug(f'{self.msg_src}: Reference package list: Download:'
                      f' {rpl_fpath}: {rpl_url}')
        except Exception as e:
            raise cr_exc.RCDownloadError(
                f'Reference package list: Download: {rpl_fpath}: {rpl_url}:'
                f' {type(e).__name__}: {e}'
            ) from e

        try:
            return cr_utl.rc_load_json(
                rpl_fpath, emheading=f'Reference package list: {rpl_fpath}'
            )
        except cr_exc.RCError as e:
            raise e
        finally:
            rpl_fpath.unlink()

    def get_dcos_conf(self):
        """Get the DC/OS aggregated configuration object.

        :return: dict, set of DC/OS shared and package specific configuration
                 templates coupled with 'key=value' substitution data
                 container:
                 {
                    'template': {
                        'package': [
                            {'path': <str>, 'content': <str>},
                             ...
                        ]
                    },
                    'values': {
                        key: value,
                        ...
                    }
                 }
        """
        # TODO: Functionality implemented in this method needs to be reused
        #       in other application parts (e.g. CmdConfigUpgrade) and so, it
        #       has been arranged as a standalone function get_dcos_conf().
        #       Thus the CmdConfigSetup is to be moved to use that standalone
        #       function instead of this method to avoid massive code
        #       duplication.
        dstor_root_url = (
            self.cluster_conf.get('distribution-storage', {}).get(
                'rooturl', ''
            )
        )
        dstor_linux_pkg_index_path = (
            self.cluster_conf.get('distribution-storage', {}).get(
                'dcosclusterpkginfopath', ''
            )
        )
        template_fname = 'dcos-config-windows.yaml'
        values_fname = 'expanded.config.full.json'

        # Unblock irrelevant local operations
        if self.cluster_conf_nop or dstor_linux_pkg_index_path == 'NOP':
            LOG.info(f'{self.msg_src}: dcos_conf: NOP')
            return {}

        # Discover relative URL to the DC/OS aggregated configuration package.
        dstor_dcoscfg_pkg_path = self.get_dstor_dcoscfgpkg_path(
            dstor_root_url, dstor_linux_pkg_index_path
        )

        dcoscfg_pkg_url = posixpath.join(
            dstor_root_url, dstor_dcoscfg_pkg_path
        )

        # Download DC/OS aggregated configuration package ...
        try:
            dcoscfg_pkg_fpath = cm_utl.download(dcoscfg_pkg_url, self.inst_storage.tmp_dpath)
            LOG.debug(f'{self.msg_src}: DC/OS aggregated config package:'
                      f' Download: {dcoscfg_pkg_url}')
        except Exception as e:
            raise cr_exc.RCDownloadError(
                f'DC/OS aggregated config package: {dcoscfg_pkg_url}:'
                f' {type(e).__name__}: {e}'
            ) from e

        # Process DC/OS aggregated configuration package.
        try:
            with tf.TemporaryDirectory(
                dir=str(self.inst_storage.tmp_dpath)
            ) as tmp_dpath:
                cm_utl.unpack(dcoscfg_pkg_fpath, tmp_dpath)
                LOG.debug(f'{self.msg_src}: DC/OS aggregated config package:'
                          f' {dcoscfg_pkg_fpath}: Extract: OK')

                values_fpath = Path(tmp_dpath).joinpath(values_fname)
                values = cr_utl.rc_load_json(
                    values_fpath,
                    emheading=f'DC/OS aggregated config: Values'
                )
                template_fpath = Path(tmp_dpath).joinpath(template_fname)
                template = self.load_dcos_conf_template(template_fpath)
        except Exception as e:
            if not isinstance(e, cr_exc.RCError):
                raise cr_exc.RCExtractError(
                    f'DC/OS aggregated config package: {dcoscfg_pkg_fpath}:'
                    f' {type(e).__name__}: {e}'
                )
            else:
                raise
        else:
            LOG.debug(f'{self.msg_src}: DC/OS aggregated config package:'
                      f' {dcoscfg_pkg_fpath}: Preprocess: OK')
            return {'template': template, 'values': values}
        finally:
            dcoscfg_pkg_fpath.unlink()

    def get_dstor_dcoscfgpkg_path(self, dstor_root_url: str,
                                  dstor_lpi_path: str):
        """Retrieve the Linux Package Index (LPI) object from the DC/OS
        distribution storage and discover a relative URL to the DC/OS
        aggregated configuration package.
        LPI is expected to be a JSON-formatted file containing descriptors for
        DC/OS distribution packages:

        {
            "<pkg-name>":{
                "filename":"<base-path>/<pkg-name>--<pkg-version>.tar.xz",
                "id":"<pkg-name>--<pkg-version>"
            },
            ...
        }

        :param dstor_root_url:         str, DC/OS distribution storage root URL
        :param dstor_lpi_path:         str, URL path to the DC/OS Linux package
                                       index object at the DC/OS distribution
                                       storage
        :return dstor_dcoscfgpkg_path: str, URL path to the DC/OS aggregated
                                       config package at the DC/OS distribution
                                       storage
        """
        # TODO: Functionality implemented in this method needs to be reused
        #       in other application parts (e.g. CmdConfigUpgrade) and so, it
        #       has been arranged as a standalone function
        #       get_dstor_dcoscfgpkg_path().
        #       Thus the CmdConfigSetup is to be moved to use that standalone
        #       function instead of this method to avoid massive code
        #       duplication.
        dcos_conf_pkg_name = 'dcos-config-win'

        # Linux package index direct URL
        lpi_url = posixpath.join(dstor_root_url, dstor_lpi_path)

        try:
            lpi_fpath = cm_utl.download(lpi_url, self.inst_storage.tmp_dpath)
            LOG.debug(f'{self.msg_src}: DC/OS Linux package index: Download:'
                      f' {lpi_url}')
        except Exception as e:
            raise cr_exc.RCDownloadError(
                f'DC/OS Linux package index: {lpi_url}: {type(e).__name__}:'
                f' {e}'
            ) from e

        try:
            lpi = cr_utl.rc_load_json(lpi_fpath,
                                      emheading='DC/OS Linux package index')

            if not isinstance(lpi, dict):
                raise cr_exc.RCInvalidError(
                    f'DC/OS Linux package index: {lpi_url}: Invalid structure'
                )

            dcos_conf_pkg_desc = lpi.get(dcos_conf_pkg_name)

            if dcos_conf_pkg_desc is None:
                raise cr_exc.RCElementError(
                    f'DC/OS Linux package index: {lpi_url}: DC/OS aggregated'
                    f' config package descriptor is missed:'
                    f' {dcos_conf_pkg_name}'
                )

            if not isinstance(dcos_conf_pkg_desc, dict):
                raise cr_exc.RCElementError(
                    f'DC/OS Linux package index: {lpi_url}: Invalid DC/OS'
                    f' aggregated config package descriptor:'
                    f' {dcos_conf_pkg_desc}'
                )

            dstor_dcoscfgpkg_path = dcos_conf_pkg_desc.get('filename')
            if dstor_dcoscfgpkg_path is None:
                raise cr_exc.RCElementError(
                    f'DC/OS Linux package index: {lpi_url}: DC/OS aggregated'
                    f' config package descriptor: Distribution storage path is'
                    f' missed: {dcos_conf_pkg_desc}'
                )
            if not isinstance(dstor_dcoscfgpkg_path, str):
                raise cr_exc.RCElementError(
                    f'DC/OS Linux package index: {lpi_url}: DC/OS aggregated'
                    f' config package descriptor: Distribution storage path:'
                    f' Invalid type: {dstor_dcoscfgpkg_path}'
                )
        finally:
            lpi_fpath.unlink()

        return dstor_dcoscfgpkg_path

    @staticmethod
    def load_dcos_conf_template(fpath: Path):
        """Load the DC/OS aggregated configuration template from disk.

        :param fpath: Path, path to template
        """
        # TODO: Functionality implemented in this method needs to be reused
        #       in other application parts (e.g. CmdConfigUpgrade) and so, it
        #       has been arranged as a standalone function
        #       load_dcos_conf_template().
        #       Thus the CmdConfigSetup is to be moved to use that standalone
        #       function instead of this method to avoid massive code
        #       duplication.
        try:
            with fpath.open() as f:
                return template.parse_str(f.read())
        except (OSError, RuntimeError) as e:
            raise cr_exc.RCError(f'DC/OS aggregated config: Template: Load:'
                                 f' {fpath}: {type(e).__name__}: {e}') from e


@cmdconf_type(CLI_COMMAND.UPGRADE)
class CmdConfigUpgrade(CommandConfig):
    """Configuration manager for the 'upgrade' command."""

    def __init__(self, **cmd_opts):
        """"""
        super(CmdConfigUpgrade, self).__init__(**cmd_opts)

        # DC/OS cluster setup parameters
        self.cluster_conf = get_cluster_conf(
            self.inst_storage.cfg_dpath, **cmd_opts
        )
        if not self.cluster_conf:
            LOG.info(f'{self.msg_src}: cluster_conf: NOP')
        LOG.debug(f'{self.msg_src}: cluster_conf: {self.cluster_conf}')

        # Reference list of DC/OS packages
        self.ref_pkg_list = get_ref_pkg_list(
            self.cluster_conf, self.inst_storage.tmp_dpath
        )
        if not self.ref_pkg_list:
            LOG.info(f'{self.msg_src}: ref_pkg_list: NOP')
        LOG.debug(f'{self.msg_src}: ref_pkg_list: {self.ref_pkg_list}')

        # DC/OS aggregated configuration object
        self.dcos_conf = get_dcos_conf(
            self.cluster_conf, self.inst_storage.tmp_dpath
        )
        if not self.dcos_conf:
            LOG.info(f'{self.msg_src}: dcos_conf: NOP')
        LOG.debug(f'{self.msg_src}: dcos_conf: {self.dcos_conf}')


@cmdconf_type(CLI_COMMAND.START)
class CmdConfigStart(CommandConfig):
    """Configuration for the 'start' command."""

    def __init__(self, **cmd_opts):
        """"""
        super(CmdConfigStart, self).__init__(**cmd_opts)

        # Make sure that the installation storage is in consistent state
        self.inst_storage.construct()


#
# Configuration utility functions
#
def get_cluster_conf(istor_cfg_dpath: Path, **cmd_opts):
    """"Get a collection of DC/OS cluster configuration options.

    :param istor_cfg_dpath: Path, absolute path to the DC/OS
                            configuration directory within the local DC/OS
                            installation storage

    :return: dict, configparser.ConfigParser.read_dict() compatible data
    """
    # Load cluster configuration file
    fpath = Path(cmd_opts.get(CLI_CMDOPT.DCOS_CLUSTERCFGPATH))

    # Unblock irrelevant local operations
    if str(fpath) == 'NOP':
        return {}

    if not fpath.is_absolute():
        if istor_cfg_dpath.exists():
            fpath = istor_cfg_dpath.joinpath(fpath)
        else:
            fpath = Path('.').resolve().joinpath(fpath)

    cluster_conf = cr_utl.rc_load_ini(
        fpath, emheading='Cluster setup descriptor'
    )

    # CLI options take precedence, if any.
    # list(tuple('ipaddr', 'port'))
    cli_master_priv_ipaddrs = [
        ipaddr.partition(':')[::2] for ipaddr in
        cmd_opts.get(CLI_CMDOPT.MASTER_PRIVIPADDR, '').split(' ') if
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
    cli_dstor_url = cmd_opts.get(CLI_CMDOPT.DSTOR_URL)
    cli_dstor_pkgrepo_path = cmd_opts.get(CLI_CMDOPT.DSTOR_PKGREPOPATH)
    cli_dstor_pkglist_path = cmd_opts.get(CLI_CMDOPT.DSTOR_PKGLISTPATH)
    cli_dstor_dcoscfg_path = cmd_opts.get(CLI_CMDOPT.DSTOR_DCOSCFGPATH)

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
    cli_local_priv_ipaddr = cmd_opts.get(CLI_CMDOPT.LOCAL_PRIVIPADDR)

    if not cluster_conf.get('local'):
        cluster_conf['local'] = {}

    if cli_local_priv_ipaddr:
        cluster_conf['local']['privateipaddr'] = cli_local_priv_ipaddr

    return cluster_conf


def get_ref_pkg_list(cluster_conf, tmp_dpath):
    """Get the current reference package list.

    :return: list, JSON-formatted data
    """
    dstor_root_url = (
        cluster_conf.get('distribution-storage', {}).get('rooturl', '')
    )
    dstor_pkglist_path = (
        cluster_conf.get('distribution-storage', {}).get('pkglistpath', '')
    )
    # Unblock irrelevant local operations
    if not cluster_conf or dstor_pkglist_path == 'NOP':
        return []

    rpl_url = posixpath.join(dstor_root_url, dstor_pkglist_path)
    try:
        rpl_fpath = cm_utl.download(rpl_url, tmp_dpath)
        LOG.debug(f'Reference package list: Download: {rpl_fpath}: {rpl_url}')
    except Exception as e:
        raise cr_exc.RCDownloadError(
            f'Reference package list: Download: {rpl_fpath}: {rpl_url}:'
            f' {type(e).__name__}: {e}'
        ) from e

    try:
        return cr_utl.rc_load_json(
            rpl_fpath, emheading=f'Reference package list: {rpl_fpath}'
        )
    except cr_exc.RCError as e:
        raise e
    finally:
        rpl_fpath.unlink()


def get_dcos_conf(cluster_conf, tmp_dpath: Path):
    """Get the DC/OS aggregated configuration object.

    :return: dict, set of DC/OS shared and package specific configuration
             templates coupled with 'key=value' substitution data
             container:
             {
                'template': {
                    'package': [
                        {'path': <str>, 'content': <str>},
                         ...
                    ]
                },
                'values': {
                    key: value,
                    ...
                }
             }
    """

    dstor_root_url = (
        cluster_conf.get('distribution-storage', {}).get('rooturl', '')
    )
    dstor_linux_pkg_index_path = (
        cluster_conf.get('distribution-storage', {}).get(
            'dcosclusterpkginfopath', ''
        )
    )
    template_fname = 'dcos-config-windows.yaml'
    values_fname = 'expanded.config.full.json'

    # Unblock irrelevant local operations
    if not cluster_conf or dstor_linux_pkg_index_path == 'NOP':
        return {}

    # Discover relative URL to the DC/OS aggregated configuration package.
    dstor_dcoscfg_pkg_path = get_dstor_dcoscfgpkg_path(
        dstor_root_url, dstor_linux_pkg_index_path, tmp_dpath
    )

    # Download DC/OS aggregated configuration package ...
    dcoscfg_pkg_url = posixpath.join(dstor_root_url, dstor_dcoscfg_pkg_path)
    try:
        dcoscfg_pkg_fpath = cm_utl.download(dcoscfg_pkg_url, tmp_dpath)
        LOG.debug(f'DC/OS aggregated config package:'
                  f' Download: {dcoscfg_pkg_url}')
    except Exception as e:
        raise cr_exc.RCDownloadError(
            f'DC/OS aggregated config package: {dcoscfg_pkg_url}:'
            f' {type(e).__name__}: {e}'
        ) from e

    # Process DC/OS aggregated configuration package.
    try:
        with tf.TemporaryDirectory(dir=str(tmp_dpath)) as tmp_dpath_:
            cm_utl.unpack(str(dcoscfg_pkg_fpath), tmp_dpath_)
            LOG.debug(f'DC/OS aggregated config package:'
                      f' {dcoscfg_pkg_fpath}: Extract: OK')

            values_fpath = Path(tmp_dpath_).joinpath(values_fname)
            values = cr_utl.rc_load_json(
                values_fpath,
                emheading=f'DC/OS aggregated config: Values'
            )
            template_fpath = Path(tmp_dpath_).joinpath(template_fname)
            template = load_dcos_conf_template(template_fpath)
    except Exception as e:
        if not isinstance(e, cr_exc.RCError):
            raise cr_exc.RCExtractError(
                f'DC/OS aggregated config package: {dcoscfg_pkg_fpath}:'
                f' {type(e).__name__}: {e}'
            )
        else:
            raise
    else:
        LOG.debug(f'DC/OS aggregated config package:'
                  f' {dcoscfg_pkg_fpath}: Preprocess: OK')
        return {'template': template, 'values': values}
    finally:
        dcoscfg_pkg_fpath.unlink()


def get_dstor_dcoscfgpkg_path(dstor_root_url: str, dstor_lpi_path: str,
                              tmp_dpath: str):
    """Retrieve the Linux Package Index (LPI) object from the DC/OS
    distribution storage and discover a relative URL to the DC/OS
    aggregated configuration package.
    LPI is expected to be a JSON-formatted file containing descriptors for
    DC/OS distribution packages:

    {
        "<pkg-name>":{
            "filename":"<base-path>/<pkg-name>--<pkg-version>.tar.xz",
            "id":"<pkg-name>--<pkg-version>"
        },
        ...
    }

    :param dstor_root_url:         str, DC/OS distribution storage root URL
    :param dstor_lpi_path:         str, URL path to the DC/OS Linux package
                                   index object at the DC/OS distribution
                                   storage
    :return tmp_dpath:             str, URL path to the DC/OS aggregated
                                   config package at the DC/OS distribution
                                   storage
    """
    dcos_conf_pkg_name = 'dcos-config-win'

    # Linux package index direct URL
    lpi_url = posixpath.join(dstor_root_url, dstor_lpi_path)
    try:
        lpi_fpath = cm_utl.download(lpi_url, tmp_dpath)
        LOG.debug(f'DC/OS Linux package index: Download: {lpi_url}')
    except Exception as e:
        raise cr_exc.RCDownloadError(
            f'DC/OS Linux package index: {lpi_url}: {type(e).__name__}: {e}'
        ) from e

    try:
        lpi = cr_utl.rc_load_json(lpi_fpath,
                                  emheading='DC/OS Linux package index')

        if not isinstance(lpi, dict):
            raise cr_exc.RCInvalidError(
                f'DC/OS Linux package index: {lpi_url}: Invalid structure'
            )

        dcos_conf_pkg_desc = lpi.get(dcos_conf_pkg_name)

        if dcos_conf_pkg_desc is None:
            raise cr_exc.RCElementError(
                f'DC/OS Linux package index: {lpi_url}: DC/OS aggregated'
                f' config package descriptor is missed:'
                f' {dcos_conf_pkg_name}'
            )

        if not isinstance(dcos_conf_pkg_desc, dict):
            raise cr_exc.RCElementError(
                f'DC/OS Linux package index: {lpi_url}: Invalid DC/OS'
                f' aggregated config package descriptor:'
                f' {dcos_conf_pkg_desc}'
            )

        dstor_dcoscfgpkg_path = dcos_conf_pkg_desc.get('filename')
        if dstor_dcoscfgpkg_path is None:
            raise cr_exc.RCElementError(
                f'DC/OS Linux package index: {lpi_url}: DC/OS aggregated'
                f' config package descriptor: Distribution storage path is'
                f' missed: {dcos_conf_pkg_desc}'
            )
        if not isinstance(dstor_dcoscfgpkg_path, str):
            raise cr_exc.RCElementError(
                f'DC/OS Linux package index: {lpi_url}: DC/OS aggregated'
                f' config package descriptor: Distribution storage path:'
                f' Invalid type: {dstor_dcoscfgpkg_path}'
            )
    finally:
        lpi_fpath.unlink()

    return dstor_dcoscfgpkg_path


def load_dcos_conf_template(fpath: Path):
    """Load the DC/OS aggregated configuration template from disk.

    :param fpath: Path, path to template
    """
    try:
        with fpath.open() as f:
            return template.parse_str(f.read())
    except (OSError, RuntimeError) as e:
        raise cr_exc.RCError(f'DC/OS aggregated config: Template: Load:'
                             f' {fpath}: {type(e).__name__}: {e}') from e
