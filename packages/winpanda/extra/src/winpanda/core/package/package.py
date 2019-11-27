"""Panda package management for Windows.

DC/OS package controller and helper type definitions.
"""
from .manifest import PackageManifest
from common import logger
from extm.extm import PkgInstExtrasManager
from svcm.nssm import WinSvcManagerNSSM


LOG = logger.get_logger(__name__)


class Package:
    """Package manager."""
    def __init__(self, pkg_id=None, istor_nodes=None, cluster_conf=None,
                 manifest=None):
        """Constructor.

        :param pkg_id:       PackageId, package ID
        :param istor_nodes:  IStorNodes, DC/OS installation storage nodes (set
                             of pathlib.Path objects)
        :param cluster_conf: dict, configparser.ConfigParser.read_dict()
                             compatible data. DC/OS cluster setup parameters
        :param manifest:     PackageManifest, DC/OS package manifest object
        """
        msg_src = self.__class__.__name__

        if manifest is not None:
            assert isinstance(manifest, PackageManifest), (
                f'Argument: manifest:'
                f' Got {type(manifest).__name__} instead of PackageManifest'
            )
            self.manifest = manifest
        else:
            self.manifest = PackageManifest(pkg_id, istor_nodes, cluster_conf)
        LOG.debug(f'{msg_src}: {self.manifest.pkg_id.pkg_id}: Manifest:'
                  f' {self.manifest}')

        if self.manifest.pkg_extcfg:
            self.ext_manager = PkgInstExtrasManager(
                ext_conf=self.manifest.pkg_extcfg
            )
        else:
            self.ext_manager = None
        LOG.debug(f'{msg_src}: {self.manifest.pkg_id.pkg_id}:'
                  f' Installation extras manager: {self.ext_manager}')

        if self.manifest.pkg_svccfg:
            self.svc_manager = WinSvcManagerNSSM(
                svc_conf=self.manifest.pkg_svccfg
            )
        else:
            self.svc_manager = None
        LOG.debug(f'{msg_src}: {self.manifest.pkg_id.pkg_id}:'
                  f' Service manager: {self.svc_manager}')
