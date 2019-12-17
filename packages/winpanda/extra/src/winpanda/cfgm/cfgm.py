"""Panda package management for Windows.

DC/OS package configuration files manager definition.
"""
from pathlib import Path
import shutil
import tempfile as tf

import jinja2 as j2

from cfgm import exceptions as cfgm_exc
from common import logger
from common.storage import ISTOR_NODE
from core import constants as cr_const
from core import exceptions as cr_exc
from core.package.manifest import PackageManifest
from core.rc_ctx import ResourceContext


LOG = logger.get_logger(__name__)


class PkgConfManager:
    """DC/OS package configuration files manager."""
    def __init__(self, pkg_manifest):
        """Constructor.

        :param pkg_manifest: PackageManifest, DC/OS package manifest object
        """
        self.msg_src = self.__class__.__name__

        assert isinstance(pkg_manifest, PackageManifest), (
            f'{self.msg_src}: Argument: pkg_manifest:'
            f' Got {type(pkg_manifest).__name__} instead of PackageManifest'
        )
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

        pkg_shrcfg_dpath = getattr(
            self._pkg_manifest.istor_nodes, ISTOR_NODE.CFG
        ).joinpath(pkg_id.pkg_name)
        LOG.debug(f'{self.msg_src}: Setup configuration: {pkg_id.pkg_name}:'
                  f' Destination directory path: {pkg_shrcfg_dpath}')

        inst_tmp_dpath = getattr(self._pkg_manifest.istor_nodes,
                                 ISTOR_NODE.TMP)
        pkg_context = self._pkg_manifest.context

        if pkg_cfg_dpath.exists():
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
            else:
                # Try to cleanup DC/OS shared configuration directory before
                # trying to create a package-specific configuration directory
                # there
                try:
                    if pkg_shrcfg_dpath.exists():
                        if pkg_shrcfg_dpath.is_dir():
                            shutil.rmtree(str(pkg_shrcfg_dpath))
                        elif pkg_shrcfg_dpath.is_file and (
                            not pkg_shrcfg_dpath.is_symlink()
                        ):
                            pkg_shrcfg_dpath.unlink()
                        else:
                            raise cr_exc.InstallationStorageError(
                                f'Setup configuration: {pkg_id.pkg_name}:'
                                f' Auto-cleanup: Removing objects other than'
                                f' regular directories and files is not'
                                f' supported: {pkg_shrcfg_dpath}'
                            )
                        LOG.debug(
                            f'{self.msg_src}: Setup configuration:'
                            f' {pkg_id.pkg_name}: Auto-cleanup:'
                            f' {pkg_shrcfg_dpath}'
                        )
                except (OSError, RuntimeError) as e:
                    raise cr_exc.InstallationStorageError(
                        f'Setup configuration: {pkg_id.pkg_name}:'
                        f' Auto-cleanup: {pkg_shrcfg_dpath}:'
                        f' {type(e).__name__}: {e}'
                    ) from e

                try:
                    with tf.TemporaryDirectory(dir=str(inst_tmp_dpath)) as tdp:

                        self._process_pkgconf_srcdir(
                            src_dpath=pkg_cfg_dpath,
                            tmp_dpath=Path(tdp),
                            context=pkg_context
                        )
                        shutil.copytree(tdp, str(pkg_shrcfg_dpath))
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

    def _process_pkgconf_srcdir(self, src_dpath, tmp_dpath, context=None):
        """Process (read, render, save) content of a DC/OS package
        configuration directory.

        :param src_dpath: pathlib.Path, path to a source configuration
                          directory
        :param tmp_dpath: pathlib.Path, path to a temporary directory to save
                          intermediate rendered content
        :param context:   ResourceContext, rendering context data object
        """
        assert isinstance(src_dpath, Path) and src_dpath.is_absolute(), (
            f'Argument: src_dpath: Absolute pathlib.Path is required:'
            f' {src_dpath}'
        )
        assert isinstance(tmp_dpath, Path) and tmp_dpath.is_absolute(), (
            f'Argument: tmp_dpath: Absolute pathlib.Path is required:'
            f' {tmp_dpath}'
        )

        if src_dpath.exists():
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

    def _process_pkgconf_srcfile(self, src_fpath, tmp_dpath, context=None):
        """Process DC/OS package configuration source file.

        :param src_fpath: pathlib.Path, path to a source configuration file
        :param tmp_dpath: pathlib.Path, path to a temporary directory to save
                          intermediate rendered content
        :param context:   ResourceContext, rendering context data object
        """
        assert isinstance(src_fpath, Path) and src_fpath.is_absolute(), (
            f'Argument: src_fpath: Absolute pathlib.Path is required:'
            f' {src_fpath}'
        )
        assert isinstance(tmp_dpath, Path) and tmp_dpath.is_absolute(), (
            f'Argument: tmp_dpath: Absolute pathlib.Path is required:'
            f' {tmp_dpath}'
        )

        if '.j2' in src_fpath.suffixes[-1:]:
            dst_fname = src_fpath.stem
            json_ready = '.json' in src_fpath.suffixes[-2:-1]
        else:
            dst_fname = src_fpath.name
            json_ready = '.json' in src_fpath.suffixes[-1:]

        if context is None:
            context_items = {}
        else:
            assert isinstance(context, ResourceContext), (
                f'Argument: context:'
                f' Got {type(context).__name__} instead of ResourceContext'
            )

            context_items = context.get_items(json_ready=json_ready)

        try:
            j2_env = j2.Environment(
                loader=j2.FileSystemLoader(str(src_fpath.parent))
            )
            j2_tmpl = j2_env.get_template(str(src_fpath.name))
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
