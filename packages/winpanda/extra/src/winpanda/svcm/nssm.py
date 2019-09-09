"""Winpanda: Windows service management: NSSM-based manager definition.

Ref:
  [1] NSSM - the Non-Sucking Service Manager
      https://nssm.cc/description
  [2] nssm/README.txt
      https://git.nssm.cc/nssm/nssm/src/master/README.txt
"""
from . import base


@base.svcm_type('nssm')
class WinSvcManagerNSSM(base.WindowsServiceManager):
    """NSSM-based Windows service manager.
    """
    def __init__(self, svcm_opts):
        """Constructor.

        :param svcm_opts: dict, service manager options:
                         {
                             'executor':     <string>,
                             'exec_path':   <string>
                         }
        """
        super(WinSvcManagerNSSM, self).__init__(svcm_opts=svcm_opts)

    # TODO: Extend the class implementation with methods in accordance with
    # TODO: the interface definition (base.WindowsServiceManager).
    # TODO: The setup method will accept the args below:
    # TODO: 1) str: svc_conf_path
    # TODO:    An absolute path on local FS to a config file of a service being
    # TODO:    installed (*.nssm, ini-style).
    # TODO: All the other methods will accept the following args:
    # TODO: 1) str: svc_name
    # TODO:    A name of a service which is already installed.
