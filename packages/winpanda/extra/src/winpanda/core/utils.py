"""Panda package management for Windows.

Core utility routine definitions.
"""
import configparser as cfp
import jinja2 as jj2
import json
from pathlib import Path
import yaml

from common import exceptions as cm_exc
from common import logger
from core.rc_ctx import ResourceContext
from core import exceptions as cr_exc
from core.package.package import Package
from typing import Dict, List, Any, Callable


LOG = logger.get_logger(__name__)


def exception_handler(func: Callable) -> Callable:
    def wrapper(fpath: Path, emheading: str = None, render: bool = False,
                context: ResourceContext = None) -> Any:
        try:
            content = func(fpath, emheading, render, context)

        except (FileNotFoundError, jj2.TemplateNotFound) as e:
            err_msg = f'Load: {fpath}'
            err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
            raise cr_exc.RCNotFoundError(err_msg) from e
        except (OSError, RuntimeError) as e:
            err_msg = f'Load: {fpath}: {type(e).__name__}: {e}'
            err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
            raise cr_exc.RCError(err_msg) from e
        except (jj2.TemplateError, yaml.YAMLError) + cr_exc.JSON_ERRORS as e:
            err_msg = f'Load: {fpath}: {type(e).__name__}: {e}'
            err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
            raise cr_exc.RCInvalidError(err_msg) from e
        else:
            return content

    return wrapper


@exception_handler
def rc_load_json(fpath: Path, emheading: str = None, render: bool = False,
                 context: ResourceContext = None) -> Any:
    """Load JSON-formatted data from a resource file. Content of a resource
    file can be pre-processed by Jinja2 rendering engine before being passed to
    JSON-parser.

    :param fpath:     Path, path to a source file.
    :param emheading: str, heading to be added to the exception's description
    :param render:    bool, perform template rendering
    :param context:   ResourceContext, rendering context data object
    :return:          json obj, JSON-formatted data
    """
    if render is True:
        jj2_env = jj2.Environment(
            loader=jj2.FileSystemLoader(str(fpath.parent))
        )
        jj2_tmpl = jj2_env.get_template(str(fpath.name))
        context_items = {} if context is None else context.get_items(json_ready=True)
        json_str = jj2_tmpl.render(**context_items)
        LOG.debug(f'rc_load_json(): json_str: {json_str}')
        j_body = json.loads(json_str, strict=False)
    else:
        with fpath.open() as fp:
            j_body = json.load(fp, strict=False)

    return j_body


@exception_handler
def rc_load_ini(fpath: Path, emheading: str = None, render: bool = False,
                context: ResourceContext = None) -> Any:
    """Load INI-formatted data from a resource file. Content of a resource
    file can be pre-processed by Jinja2 rendering engine before being passed to
    INI-parser.

    :param fpath:     pathlib.Path, path to a source file
    :param emheading: str, heading to be added to the exception's description
    :param render:    bool, perform template rendering
    :param context:   ResourceContext, rendering context data object
    :return:          dict, configparser.ConfigParser.read_dict() compatible
                      data.
    """
    cfg_parser = cfp.ConfigParser()

    if render is True:
        jj2_env = jj2.Environment(
            loader=jj2.FileSystemLoader(str(fpath.parent))
        )
        jj2_tmpl = jj2_env.get_template(str(fpath.name))
        context_items = {} if context is None else context.get_items()
        ini_str = jj2_tmpl.render(**context_items)
        LOG.debug(f'rc_load_ini(): ini_str: {ini_str}')
        cfg_parser.read_string(ini_str, source=str(fpath))
    else:
        with fpath.open() as fp:
            cfg_parser.read_file(fp)

    return {k: dict(v) for k, v in cfg_parser.items()}


@exception_handler
def rc_load_yaml(fpath: Path, emheading: str = "", render: bool = False,
                 context: ResourceContext = None) -> Any:
    """Load YAML-formatted data from a resource file. Content of a resource
    file can be pre-processed by Jinja2 rendering engine before being passed to
    YAML-parser.

    :param fpath:     pathlib.Path, path to a source file.
    :param emheading: str, heading to be added to the exception's description
    :param render:    bool, perform template rendering
    :param context:   ResourceContext, rendering context data object
    :return:          yaml obj, YAML-formatted data
    """
    if render is True:
        jj2_env = jj2.Environment(
            loader=jj2.FileSystemLoader(str(fpath.parent))
        )
        jj2_tmpl = jj2_env.get_template(str(fpath.name))
        context_items = {} if context is None else context.get_items()
        yaml_str = jj2_tmpl.render(**context_items)
        LOG.debug(f'rc_load_yaml(): yaml_str: {yaml_str}')
        y_body = yaml.safe_load(yaml_str)
    else:
        with fpath.open() as fp:
            y_body = yaml.safe_load(fp)

    return y_body


def pkg_sort_by_deps(packages: Dict[str, Package]) -> List[Package]:
    """Get a list of package manager objects sorted by mutual dependencies of
    their associated DC/OS packages.
    Ref:
        [1] Topological sorting.
            https://en.wikipedia.org/wiki/Topological_sorting

    :param packages: dict(<pkg_name>: Package), set of DC/OS package manager
                     objects
    :return:         list(Package), ordered sequence of DC/OS package manager
                     objects
    """
    msg_src = 'pkg_sort_by_deps()'
    pkg_names_order_base = ['vcredist', 'nssm', 'bootstrap']
    LOG.debug(f'{msg_src}: pkg_names_order_base: {pkg_names_order_base}')

    pkg_names_provided = set(packages)
    LOG.debug(f'{msg_src}: pkg_names_provided: {pkg_names_provided}')

    pkg_names_required = set(pkg_names_order_base)
    LOG.debug(f'{msg_src}: pkg_names_required: {pkg_names_required}')

    pkg_names_other = set(pkg_names_provided)
    pkg_names_other.difference_update(pkg_names_required)

    LOG.debug(f'{msg_src}: pkg_names_other: {pkg_names_other}')

    pkg_names_missed = pkg_names_required.difference(pkg_names_provided)
    LOG.debug(f'{msg_src}: pkg_names_missed: {pkg_names_missed}')

    if pkg_names_missed:
        raise cm_exc.InstallationError(
            f'Resolve DC/OS packages mutual dependencies: Required packages'
            f' not found within DC/OS installation local package repository:'
            f' {pkg_names_missed}'
        )

    packages_sorted = [
        packages[pkg_name] for pkg_name in pkg_names_order_base
    ]
    packages_sorted[len(packages_sorted):] = [
        packages[pkg_name] for pkg_name in sorted(pkg_names_other)
    ]

    # TODO: Implement topological sorting algorithm using package mutual
    #       dependencies information from the 'requires' element of the
    #       pkginfo.json file provided with a package instead of the
    #       placeholder implementation above.

    return packages_sorted
