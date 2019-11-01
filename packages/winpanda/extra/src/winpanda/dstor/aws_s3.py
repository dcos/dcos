"""Winpanda: DC/OS distribution storage: AWS S3 driver definition.
"""
from . import base


@base.dstor_type('aws-s3-http')
class DStorAWSS3HTTP(base.DistStorage):
    """AWS S3 DC/OS distribution storage employing HTTP-communications.
    """
    def __init__(self, dse_opts):
        """Constructor.

        :param dse_opts: dict, distribution storage endpoint options:
                         {
                             'scheme':     <string>,
                             'accessid':   <string>,
                             'secret':     <string>,
                             'host':       <string>,
                             'port':       <int>,
                             'resourceid': <string>
                         }
        """
        super(DStorAWSS3HTTP, self).__init__(dse_opts=dse_opts)

        self.key_id = self.dse_opts.get('accessid', '')
        self.secret_key = self.dse_opts.get('secret', '')
        self.region = self.dse_opts.get('host', '')
        self.port = self.dse_opts.get('port', 0)
        self.bucket = self.dse_opts.get('resourceid', '')

        self.ds_client = None

    # TODO: Extend the class implementation with methods in accordance with
    # TODO: the interface definition (base.DistStorage).
    # TODO: The get_package method will accept the next args:
    # TODO: 1) str: pkg_id
    # TODO:    Ref: https://github.com/dcos/dcos/blob/master/pkgpanda/docs/package_concepts.md
    # TODO: 2) str: inst_root_path
    # TODO:    An absolute path on local FS, where to install package to.
