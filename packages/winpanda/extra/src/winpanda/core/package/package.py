"""Panda package management for Windows.

DC/OS package controller and helper type definitions.
"""
from .manifest import PackageManifest
from svcm.nssm import WinSvcManagerNSSM


class Package:
    """Package manager."""
    def __init__(self, pkg_id, istor_nodes, cluster_conf):
        """Constructor.

        :param pkg_id:       PackageId, package ID
        :param istor_nodes:  IStorNodes, DC/OS installation storage nodes (set
                             of pathlib.Path objects)
        :param cluster_conf: dict, configparser.ConfigParser.read_dict()
                             compatible data. DC/OS cluster setup parameters
        """
        self.manifest = PackageManifest(pkg_id, istor_nodes, cluster_conf)

        # TODO: The integration point for extra installation options manager
        # if self.manifest.pkg_extcfg:
        #     self.ext_manager = PkgInstExtrasManager(
        #         ext_conf=self.manifest.pkg_extcfg
        #     )
        # else:
        #     self.ext_manager = None
        self.ext_manager = None

        if self.manifest.pkg_svccfg:
            self.svc_manager = WinSvcManagerNSSM(
                svc_conf=self.manifest.pkg_svccfg
            )
        else:
            self.svc_manager = None
