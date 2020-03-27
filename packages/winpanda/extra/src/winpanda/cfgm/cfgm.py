"""Panda package management for Windows.

DC/OS package configuration files manager definition.
"""
from pathlib import Path
import tempfile as tf

import jinja2 as j2

from cfgm import exceptions as cfgm_exc
from common import logger
from common.storage import ISTOR_NODE
from common.utils import transfer_files
from core import constants as cr_const
from core import exceptions as cr_exc
from core.package.manifest import PackageManifest
from core.rc_ctx import ResourceContext


LOG = logger.get_logger(__name__)


class PkgConfManager:
    """DC/OS package configuration files manager."""

    def __init__(self, pkg_manifest: PackageManifest):
        """Constructor.

        :param pkg_manifest: PackageManifest, DC/OS package manifest object
        """
        self.msg_src = self.__class__.__name__
        self._pkg_manifest = pkg_manifest

    def __str__(self):
        return str(f'{self.__class__.__name__}({self._pkg_manifest})')

    def setup_conf(self):
        """Setup configuration objects for a DC/OS package."""
        pkg_id = self._pkg_manifest.pkg_id
        pkg_cfg_dpath = getattr(
            self._pkg_manifest.istor_nodes, ISTOR_NODE.PKGREPO
        ).joinpath(pkg_id.pkg_id, cr_const.PKG_CFG_DNAME)
        LOG.debug(f'{self.msg_src}: Setup configuration: {pkg_id.pkg_name}:'
                  f' Source directory path: {pkg_cfg_dpath}')

        config_dir = getattr(self._pkg_manifest.istor_nodes, ISTOR_NODE.CFG)
        pkg_shrcfg_dpath = config_dir.joinpath(pkg_id.pkg_name)
        LOG.debug(f'{self.msg_src}: Setup configuration: {pkg_id.pkg_name}:'
                  f' Destination directory path: {pkg_shrcfg_dpath}')

        pkg_context = self._pkg_manifest.context

        if pkg_cfg_dpath.exists():
            # Check source is a directory
            if pkg_cfg_dpath.is_symlink():
                err_msg = (f'Source directory: Symlink conflict:'
                           f' {pkg_cfg_dpath}')
                raise cfgm_exc.PkgConfInvalidError(err_msg)
            elif pkg_cfg_dpath.is_reserved():
                err_msg = (f'Source directory: Reserved name conflict:'
                           f' {pkg_cfg_dpath}')
                raise cfgm_exc.PkgConfInvalidError(err_msg)
            elif not pkg_cfg_dpath.is_dir():
                err_msg = (f'Source directory: Not a directory:'
                           f' {pkg_cfg_dpath}')
                raise cfgm_exc.PkgConfInvalidError(err_msg)

            # Ensure destination exists and is a directory
            try:
                pkg_shrcfg_dpath.mkdir(parents=True, exist_ok=True)
            except FileExistsError:
                raise cr_exc.InstallationStorageError(
                    f'Setup configuration: {pkg_id.pkg_name}:'
                    f' {pkg_shrcfg_dpath} exists but is not a directory'
                )

            try:
                with tf.TemporaryDirectory(dir=str(config_dir)) as tdp:

                    self._process_pkgconf_srcdir(
                        src_dpath=pkg_cfg_dpath,
                        tmp_dpath=Path(tdp),
                        context=pkg_context
                    )
                    transfer_files(tdp, str(pkg_shrcfg_dpath))
                    LOG.debug(
                        f'{self.msg_src}: Setup configuration:'
                        f' {pkg_id.pkg_name}: Save: {pkg_shrcfg_dpath}: OK'
                    )
            except (OSError, RuntimeError) as e:
                err_msg = (f'Setup configuration: {pkg_id.pkg_name}:'
                           f' Process configuration sources:'
                           f' {pkg_cfg_dpath}: {type(e).__name__}: {e}')
                raise cfgm_exc.PkgConfManagerError(err_msg)
        else:
            err_msg = f'Source directory: Not found: {pkg_cfg_dpath}'
            raise cfgm_exc.PkgConfNotFoundError(err_msg)

    def _process_pkgconf_srcdir(self, src_dpath: Path, tmp_dpath: Path,
                                context=None):
        """Process (read, render, save) content of a DC/OS package
        configuration directory.

        :param src_dpath: Path, path to a source configuration
                          directory
        :param tmp_dpath: Path, path to a temporary directory to save
                          intermediate rendered content
        :param context:   ResourceContext, rendering context data object
        """
        if not src_dpath.exists():
            return

        if src_dpath.is_symlink():
            raise cfgm_exc.PkgConfInvalidError(f'Symlink conflict:'
                                               f' {src_dpath}')
        elif src_dpath.is_reserved():
            raise cfgm_exc.PkgConfInvalidError(f'Reserved name conflict:'
                                               f' {src_dpath}')
        elif not src_dpath.is_dir():
            raise cfgm_exc.PkgConfInvalidError(f'Not a directory:'
                                               f' {src_dpath}')
        else:
            for sub_path in src_dpath.iterdir():
                if sub_path.is_dir():
                    sub_tmp_dpath = tmp_dpath.joinpath(sub_path.name)
                    sub_tmp_dpath.mkdir()
                    self._process_pkgconf_srcdir(
                        src_dpath=sub_path,
                        tmp_dpath=sub_tmp_dpath,
                        context=context
                    )
                else:
                    self._process_pkgconf_srcfile(
                        src_fpath=sub_path,
                        tmp_dpath=tmp_dpath,
                        context=context
                    )

    def _process_pkgconf_srcfile(self, src_fpath: Path, tmp_dpath: Path,
                                 context: ResourceContext=None):
        """Process DC/OS package configuration source file.

        :param src_fpath: Path, path to a source configuration file
        :param tmp_dpath: Path, path to a temporary directory to save
                          intermediate rendered content
        :param context:   ResourceContext, rendering context data object
        """
        if '.j2' in src_fpath.suffixes[-1:]:
            dst_fname = src_fpath.stem
            json_ready = '.json' in src_fpath.suffixes[-2:-1]
        else:
            dst_fname = src_fpath.name
            json_ready = '.json' in src_fpath.suffixes[-1:]

        try:
            j2_env = j2.Environment(
                loader=j2.FileSystemLoader(str(src_fpath.parent))
            )
            j2_tmpl = j2_env.get_template(str(src_fpath.name))
            context_items = {} if context is None else context.get_items(
                json_ready=json_ready)
            rendered_str = j2_tmpl.render(**context_items)
            LOG.debug(f'{self.msg_src}: Process configuration file:'
                      f' {src_fpath}: Rendered content: {rendered_str}')

            dst_fpath = tmp_dpath.joinpath(dst_fname)
            dst_fpath.write_text(rendered_str, encoding='utf-8')
            LOG.debug(f'{self.msg_src}: Process configuration file:'
                      f' {src_fpath}: Save: {dst_fpath}')
        except (FileNotFoundError, j2.TemplateNotFound) as e:
            err_msg = f'Load: {src_fpath}'
            raise cfgm_exc.PkgConfFileNotFoundError(err_msg) from e
        except (OSError, RuntimeError) as e:
            err_msg = f'Load: {src_fpath}: {type(e).__name__}: {e}'
            raise cfgm_exc.PkgConfError(err_msg) from e
        except j2.TemplateError as e:
            err_msg = f'Load: {src_fpath}: {type(e).__name__}: {e}'
            raise cfgm_exc.PkgConfFileInvalidError(err_msg) from e
