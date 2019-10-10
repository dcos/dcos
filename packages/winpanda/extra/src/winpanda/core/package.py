"""Panda package management for Windows.

DC/OS package controller and helper type definitions.
"""
import json

from common import exceptions as cm_exc
from common import logger
from core import exceptions as cr_exc
from svcm.nssm import WinSvcManagerNSSM


LOG = logger.get_logger(__name__)


class PackageId:
    """DC/OS package ID object.

    Ref:
      [1] https://github.com/dcos/dcos/blob/master/pkgpanda/docs/\
          package_concepts.md
    """
    _separator = '--'

    def __init__(self, pkg_id=None, pkg_name=None, pkg_version=None):
        """Constructor.

        :param pkg_id:      str, string representation of a DC/OS package ID
        :param pkg_name:    str, DC/OS package name
        :param pkg_version: str, DC/OS package version
        """
        # TODO: Add character set validation for arguments [1]
        if pkg_id is not None:
            pkg_name, sep, pkg_version = (
                str(pkg_id).partition(sep=self._separator)
            )

            if not (sep and pkg_name and pkg_version):
                raise ValueError(f'Invalid package ID: {pkg_id}')

            self.pkg_name = pkg_name
            self.pkg_version = pkg_version
            self.pkg_id = pkg_id
        elif pkg_name is not None and pkg_version is not None:
            self.pkg_name = str(pkg_name)
            self.pkg_version = str(pkg_version)
            self.pkg_id = f'{self.pkg_name}{self._separator}{self.pkg_version}'

    def __str__(self):
        return self.pkg_id

    @classmethod
    def parse(cls, pkg_id):
        """Deconstruct a package ID string into elements.

        :param pkg_id: str, string representation of a DC/OS package ID
        :return:       tuple(str, str), two tuple of package ID elements -
                       (pkg_name, pkg_version)
        """
        pkg_name, sep, pkg_version = str(pkg_id).partition(sep=cls._separator)
        if not (sep and pkg_name and pkg_version):
            raise ValueError(f'Invalid package ID: {pkg_id}')

        return pkg_name, pkg_version


class PackageManifest:
    """Package manifest container."""
    def __init__(self, pkg_id=None):
        """Constructor.

        :param pkg_id: PackageId, DC/OS package ID object
        """
        assert isinstance(pkg_id, PackageId), (
            f'Arg: pkg_id: Got {type(pkg_id).__name__} instead of PackageId'
        )
        self.pkg_id = pkg_id

    def _get_dict(self):
        """Construct a native representation of the manifest (dict)."""
        manifest = {
            'pkg_id': self.pkg_id
        }

        return manifest

    def json(self):
        """Construct JSON representation of the manifest."""
        return json.dumps(self._get_dict(), indent=4, sort_keys=True)

    @ classmethod
    def load(cls, path):
        """Load package manifest from a file.

        :param path: pathlib.Path, path to a manifest source file.
        :return:     dict, JSON-formatted package manifest.
        """
        try:
            with path.open() as fp:
                manifest = json.load(fp)
        except FileNotFoundError:
            err_msg = f'Package manifest: Read: {path}'
            raise cr_exc.RCNotFoundError(err_msg)
        except OSError as e:
            err_msg = f'Package manifest: Read: {type(e).__name__}: {e}'
            raise cr_exc.RCInvalidError(err_msg)
        except cm_exc.JSON_ERRORS as e:
            err_msg = f'Package manifest: Read: {type(e).__name__}: {e}'
            raise cr_exc.RCInvalidError(err_msg)
        else:
            # TODO: Add content verification. Raise cr_exc.RCInvalidError, if
            #       conformance was not confirmed.
            pass

        LOG.debug(f'Package manifest: Loaded OK: {path}')

        return manifest

    def save(self, path):
        """Save package manifest to a file.

        :param path: pathlib.Path, path to a manifest destination file.
        """
        try:
            with path.open(mode='w') as fp:
                json.dump(self._get_dict(), fp)
        except OSError as e:
            err_msg = f'Package manifest: Save: {type(e).__name__}: {e}'
            raise cr_exc.RCInvalidError(err_msg)

        LOG.debug(f'Package manifest: Saved OK: {path}')


class Package:
    """Package manager"""

    def __init__(self, pkg_id, cluster_conf):
        """Constructor.

        :param pkg_id:       PackageId, DC/OS package ID object
        :param cluster_conf: dict, DC/OS cluster-specific parameters
        """
        self.pkg_id = pkg_id
        self.cluster_conf = dict(
            master_ip=cluster_conf.get('master_priv_ipaddr'),
            local_ip=cluster_conf.get('local-priv-ipaddr')
        )
        self.svc_manager = WinSvcManagerNSSM(
            pkg_id=self.pkg_id,
            cluster_conf=self.cluster_conf
        )
