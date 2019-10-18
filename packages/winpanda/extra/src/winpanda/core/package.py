"""Panda package management for Windows.

DC/OS package controller and helper type definitions.
"""
import configparser as cfp
import json
from pathlib import Path

from common import logger
from core import exceptions as cr_exc
from core import utils as cr_utl
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
            pkg_name, sep, pkg_version = str(pkg_id).partition(self._separator)

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
    _pkginfo_fpath = 'pkginfo.json'
    _pkg_ini_fpath = 'etc/package.ini'
    _svc_cfg_fpath = 'etc/package.nssm'

    def __init__(self, pkg_id, pkgrepo_dpath, pkgactive_dpath,
                 pkg_info=None, pkg_ini=None, svc_conf=None):
        """Constructor.

        :param pkg_id:          PackageId, package ID
        :param pkgrepo_dpath:   pathlib.Path, local package repository dir
        :param pkgactive_dpath: pathlib.Path, active packages index dir
        :param pkg_info: dict, package info descriptor from DC/OS package build
                         system
        :param pkg_ini:  dict, package initialization/pre-install options
                         (configparser.ConfigParser.read_dict() compatible)
        :param svc_conf: dict, package system service options
                         (configparser.ConfigParser.read_dict() compatible)
        """
        assert isinstance(pkg_id, PackageId), (
            f'Argument: pkg_id:'
            f' Got {type(pkg_id).__name__} instead of PackageId'
        )
        assert (isinstance(pkgrepo_dpath, Path) and
                pkgrepo_dpath.is_absolute() and
                pkgrepo_dpath.is_dir()), (f'Argument: pkgrepo_dpath: Absolute'
                                          f' directory pathlib.Path is'
                                          f' required: {pkgrepo_dpath}')
        assert (isinstance(pkgactive_dpath, Path) and
                pkgactive_dpath.is_absolute() and
                pkgactive_dpath.is_dir()), (f'Argument: pkgactive_dpath:'
                                            f' Absolute directory pathlib.Path'
                                            f' is required: {pkgactive_dpath}')
        self.pkg_id = pkg_id
        self.pkgrepo_dpath = pkgrepo_dpath
        self.pkgactive_dpath = pkgactive_dpath

        # TODO: Add package info descriptor handling
        # self.pkg_info = (
        #     pkg_info if isinstance(pkg_info, dict) else self._load_pkg_info()
        # )
        self.pkg_info = {}
        # TODO: Add package initialization descriptor handling
        # self.pkg_ini = (
        #     pkg_ini if isinstance(pkg_ini, dict) else self._load_pkg_ini()
        # )
        self.pkg_ini = {}
        self.svc_conf = (
            svc_conf if isinstance(svc_conf, dict) else self._load_svc_conf()
        )
        # TODO: Add content verification (jsonschema) for self.body. Raise
        #       ValueError, if conformance was not confirmed.

    def __str__(self):
        return str(self.pkg_id)

    @property
    def body(self):
        """"""
        return {
            'pkg_id': str(self.pkg_id),
            'pkgrepo_dpath': str(self.pkgrepo_dpath),
            'pkgactive_dpath': str(self.pkgactive_dpath),
            'pkg_info': self.pkg_info,
            'pkg_ini': self.pkg_ini,
            'svc_conf': self.svc_conf,
        }

    def _load_pkg_info(self):
        """Load package info descriptor from a file."""
        fpath = self.pkgrepo_dpath.joinpath(str(self.pkg_id),
                                            self._pkginfo_fpath)
        return cr_utl.rc_load_json(fpath, emheading='Package info descriptor')

    def _load_pkg_ini(self):
        """Load package initialization/pre-install options from a file."""
        fpath = self.pkgrepo_dpath.joinpath(str(self.pkg_id),
                                            self._pkg_ini_fpath)

        return cr_utl.rc_load_ini(fpath, emheading='Package ini descriptor')

    def _load_svc_conf(self):
        """Load package system service options from a file."""
        fpath = self.pkgrepo_dpath.joinpath(str(self.pkg_id),
                                            self._svc_cfg_fpath)

        return cr_utl.rc_load_ini(fpath, emheading='Package svc descriptor')

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
                pkgrepo_dpath=Path(m_body.get('pkgrepo_dpath')),
                pkgactive_dpath=Path(m_body.get('pkgactive_dpath')),
                pkg_info=m_body.get('pkg_info'),
                pkg_ini=m_body.get('pkg_ini'),
                svc_conf=m_body.get('svc_conf'),
            )
            LOG.debug(f'Package manifest: Load: {fpath}')
        except (ValueError, AssertionError) as e:
            err_msg = (f'Package manifest: Load:'
                       f' {fpath}: {type(e).__name__}: {e}')
            raise cr_exc.RCInvalidError(err_msg)

        return manifest

    def save(self):
        """Save package manifest to a file within the active packages index."""
        fpath = self.pkgactive_dpath.joinpath(f'{self.pkg_id}.json')

        try:
            with fpath.open(mode='w') as fp:
                json.dump(self.body, fp)
        except (OSError, RuntimeError) as e:
            err_msg = f'Package manifest: Save: {type(e).__name__}: {e}'
            raise cr_exc.RCError(err_msg)

        LOG.debug(f'Package manifest: Save: {fpath}')


class Package:
    """Package manager."""
    def __init__(self, pkg_id, pkgrepo_dpath, pkgactive_dpath, cluster_conf):
        """Constructor.

        :param pkg_id:          PackageId, package ID
        :param pkgrepo_dpath:   pathlib.Path, local package repository dir
        :param pkgactive_dpath: pathlib.Path, active packages index dir
        :param cluster_conf:    dict, configparser.ConfigParser.read_dict()
                                compatible data. DC/OS cluster setup parameters
        """
        self.manifest = PackageManifest(pkg_id, pkgrepo_dpath, pkgactive_dpath)

        self.ini_manager = None

        self.svc_conf = cfp.ConfigParser()
        self.svc_conf.read_dict(self.manifest.svc_conf)
        self.cluster_conf = cfp.ConfigParser()
        self.cluster_conf.read_dict(cluster_conf)
        self.svc_manager = WinSvcManagerNSSM(
            svc_conf=self.svc_conf,
            cluster_conf=self.cluster_conf
        )
