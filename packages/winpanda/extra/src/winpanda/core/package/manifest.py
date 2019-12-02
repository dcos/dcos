"""Panda package management for Windows.

DC/OS package manifest type definition.
"""
import json
from pathlib import Path

from .id import PackageId
from common import logger
from common.storage import ISTOR_NODE, IStorNodes
from core import exceptions as cr_exc
from core.rc_ctx import ResourceContext
from core import utils as cr_utl


LOG = logger.get_logger(__name__)


class PackageManifest:
    """Package manifest container."""
    _pkginfo_fpath = 'pkginfo.json'
    _pkg_extcfg_fpath = 'etc/{pkg_name}.extra.j2'
    _pkg_svccfg_fpath = 'etc/{pkg_name}.nssm.j2'

    def __init__(self, pkg_id, istor_nodes, cluster_conf,
                 pkg_info=None, pkg_extcfg=None, pkg_svccfg=None):
        """Constructor.

        :param pkg_id:       PackageId, package ID
        :param istor_nodes:  IStorNodes, DC/OS installation storage nodes (set
                             of pathlib.Path objects)
        :param cluster_conf: dict, configparser.ConfigParser.read_dict()
                             compatible data. DC/OS cluster setup parameters
        :param pkg_info:     dict, package info descriptor from DC/OS package
                             build system
        :param pkg_extcfg:   dict, extra package installation options
        :param pkg_svccfg:   dict, package system service options
                             (configparser.ConfigParser.read_dict() compatible)
        # :param context:    dict, package resources rendering context
        """
        assert isinstance(pkg_id, PackageId), (
            f'Argument: pkg_id:'
            f' Got {type(pkg_id).__name__} instead of PackageId'
        )
        assert isinstance(istor_nodes, IStorNodes), (
            f'Argument: istor_nodes:'
            f' Got {type(istor_nodes).__name__} instead of IStorNodes'
        )
        assert isinstance(cluster_conf, dict), (
            f'Argument: cluster_conf:'
            f'Got {type(cluster_conf).__name__} instead of dict'
        )

        self._pkg_id = pkg_id
        self._istor_nodes = istor_nodes
        self._context = ResourceContext(istor_nodes, cluster_conf, pkg_id)

        # Load package info descriptor
        self._pkg_info = pkg_info if pkg_info is not None else (
            self._load_pkg_info()
        )
        # Load package extra installation options descriptor
        self._pkg_extcfg = pkg_extcfg if pkg_extcfg is not None else (
            self._load_pkg_extcfg()
        )
        # Load package system service options descriptor
        self._pkg_svccfg = pkg_svccfg if pkg_svccfg is not None else (
                self._load_pkg_svccfg()
        )
        # TODO: Add content verification (jsonschema) for self.body. Raise
        #       ValueError, if conformance was not confirmed.

    def __str__(self):
        return str(self.body)

    @property
    def body(self):
        """"""
        return {
            'pkg_id': self._pkg_id.pkg_id,
            'context': self._context.as_dict(),
            'pkg_info': self._pkg_info,
            'pkg_extcfg': self._pkg_extcfg,
            'pkg_svccfg': self._pkg_svccfg,
        }

    @property
    def pkg_id(self):
        """"""
        return self._pkg_id

    @property
    def istor_nodes(self):
        """"""
        return self._pkg_id

    @property
    def pkg_info(self):
        """"""
        return self._pkg_info

    @property
    def pkg_extcfg(self):
        """"""
        return self._pkg_extcfg

    @property
    def pkg_svccfg(self):
        """"""
        return self._pkg_svccfg

    def _load_pkg_info(self):
        """Load package info descriptor from a file.

        :return: dict, package info descriptor
        """
        fpath = getattr(self._istor_nodes, ISTOR_NODE.PKGREPO).joinpath(
            self._pkg_id.pkg_id, self._pkginfo_fpath
        )
        try:
            pkg_info = cr_utl.rc_load_json(
                fpath, emheading='Package info descriptor',
                render=True, context=self._context
            )
        except cr_exc.RCNotFoundError:
            pkg_info = {}

        return pkg_info

    def _load_pkg_extcfg(self):
        """Load package extra installation options from a file.

        :return: dict, package extra installation options descriptor
        """
        fpath = getattr(self._istor_nodes, ISTOR_NODE.PKGREPO).joinpath(
            self._pkg_id.pkg_id, self._pkg_extcfg_fpath.format(
                pkg_name=self._pkg_id.pkg_name
            )
        )
        try:
            pkg_extcfg = cr_utl.rc_load_yaml(
                fpath, emheading='Package inst extra descriptor',
                render=True, context=self._context
            )
        except cr_exc.RCNotFoundError:
            pkg_extcfg = {}

        return pkg_extcfg

    def _load_pkg_svccfg(self):
        """Load package system service options from a file.

        :return: dict, package system service descriptor
        """
        fpath = getattr(self._istor_nodes, ISTOR_NODE.PKGREPO).joinpath(
            self._pkg_id.pkg_id, self._pkg_svccfg_fpath.format(
                pkg_name=self._pkg_id.pkg_name
            )
        )
        try:
            pkg_svccfg = cr_utl.rc_load_ini(
                fpath, emheading='Package service descriptor',
                render=True, context=self._context
            )
        except cr_exc.RCNotFoundError:
            pkg_svccfg = {}

        return pkg_svccfg

    def json(self):
        """Construct JSON representation of the manifest."""
        return json.dumps(self.body, indent=4, sort_keys=True)

    @ classmethod
    def load(cls, fpath):
        """Load package manifest from a file.

        :param fpath: pathlib.Path, path to a JSON-formatted manifest file.
        :return:      dict, package manifest.
        """
        m_body = cr_utl.rc_load_json(fpath, emheading='Package manifest')

        try:
            manifest = cls(
                pkg_id=PackageId(pkg_id=m_body.get('pkg_id')),
                istor_nodes=IStorNodes(
                    **{
                        k: Path(v) for k, v in m_body.get(
                            'context'
                        ).get('istor_nodes').items()
                    }
                ),
                cluster_conf=m_body.get('context').get('cluster_conf'),
                pkg_info=m_body.get('pkg_info'),
                pkg_extcfg=m_body.get('pkg_extcfg'),
                pkg_svccfg=m_body.get('pkg_svccfg'),
            )
            LOG.debug(f'Package manifest: Load: {fpath}')
        except (ValueError, AssertionError) as e:
            err_msg = (f'Package manifest: Load:'
                       f' {fpath}: {type(e).__name__}: {e}')
            raise cr_exc.RCInvalidError(err_msg) from e

        return manifest

    def save(self):
        """Save package manifest to a file within the active packages index."""
        fpath = getattr(self._istor_nodes, ISTOR_NODE.PKGACTIVE).joinpath(
            f'{self._pkg_id.pkg_id}.json'
        )

        try:
            with fpath.open(mode='w') as fp:
                json.dump(self.body, fp)
        except (OSError, RuntimeError) as e:
            err_msg = f'Package manifest: Save: {type(e).__name__}: {e}'
            raise cr_exc.RCError(err_msg) from e

        LOG.debug(f'Package manifest: Save: {fpath}')
