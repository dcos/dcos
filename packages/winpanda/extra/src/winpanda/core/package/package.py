"""Panda package management for Windows.

DC/OS package controller and helper type definitions.
"""
from .manifest import PackageManifest
from cfgm.cfgm import PkgConfManager
from common import logger
from extm.extm import PkgInstExtrasManager
from svcm.nssm import WinSvcManagerNSSM


LOG = logger.get_logger(__name__)


class Package:
    """Package manager."""
    def __init__(self, pkg_id=None, istor_nodes=None, cluster_conf=None,
                 extra_context=None, manifest=None):
        """Constructor.

        :param pkg_id:        PackageId, package ID
        :param istor_nodes:   IStorNodes, DC/OS installation storage nodes (set
                              of pathlib.Path objects)
        :param cluster_conf:  dict, configparser.ConfigParser.read_dict()
                              compatible data. DC/OS cluster setup parameters
        :param extra_context: dict, extra 'key=value' data to be added to the
                              resource rendering context
        :param manifest:      PackageManifest, DC/OS package manifest object
        """
        self.msg_src = self.__class__.__name__

        if manifest is not None:
            assert isinstance(manifest, PackageManifest), (
                f'Argument: manifest:'
                f' Got {type(manifest).__name__} instead of PackageManifest'
            )
            self.manifest = manifest
        else:
            self.manifest = PackageManifest(
                pkg_id=pkg_id, istor_nodes=istor_nodes,
                cluster_conf=cluster_conf, extra_context=extra_context
            )

        LOG.debug(f'{self.msg_src}: {self.manifest.pkg_id.pkg_id}: Manifest:'
                  f' {self.manifest}')

        self.cfg_manager = PkgConfManager(pkg_manifest=self.manifest)
        LOG.debug(f'{self.msg_src}: {self.manifest.pkg_id.pkg_id}:'
                  f' Package configuration manager: {self.cfg_manager}')

        if self.manifest.pkg_extcfg:
            self.ext_manager = PkgInstExtrasManager(pkg_manifest=self.manifest)
        else:
            self.ext_manager = None
        LOG.debug(f'{self.msg_src}: {self.manifest.pkg_id.pkg_id}:'
                  f' Installation extras manager: {self.ext_manager}')

        if self.manifest.pkg_svccfg:
            self.svc_manager = WinSvcManagerNSSM(
                svc_conf=self.manifest.pkg_svccfg
            )
        else:
            self.svc_manager = None
        LOG.debug(f'{self.msg_src}: {self.manifest.pkg_id.pkg_id}:'
                  f' Service manager: {self.svc_manager}')
