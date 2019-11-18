"""Panda package management for Windows.

Core utility routine definitions.
"""
import configparser as cfp
import jinja2 as jj2
import json
from pathlib import Path
import yaml

from common import logger
from core import exceptions as cr_exc


LOG = logger.get_logger(__name__)


def rc_load_json(fpath, emheading=None, render=False, **context):
    """Load JSON-formatted data from a resource file. Content of a resource
    file can be pre-processed by Jinja2 rendering engine before being passed to
    JSON-parser.

    :param fpath:     pathlib.Path, path to a source file.
    :param emheading: str, heading to be added to the exception's description
    :param render:    bool, perform template rendering
    :param context:   dict, rendering context for jinja2.Temlate.render()
    :return:          json obj, JSON-formatted data
    """
    assert isinstance(fpath, Path) and fpath.is_absolute(), (
        f'Argument: fpath: Absolute pathlib.Path is required: {fpath}'
    )

    try:
        if render is True:
            jj2_env = jj2.Environment(
                loader=jj2.FileSystemLoader(str(fpath.parent))
            )
            jj2_tmpl = jj2_env.get_template(str(fpath.name))
            json_str = jj2_tmpl.render(**context)
            LOG.debug(f'rc_load_json(): json_str: {json_str}')
            j_body = json.loads(json_str, strict=False)
        else:
            with fpath.open() as fp:
                j_body = json.load(fp, strict=False)
    except (FileNotFoundError, jj2.TemplateNotFound) as e:
        err_msg = f'Load: {fpath}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCNotFoundError(err_msg) from e
    except (OSError, RuntimeError) as e:
        err_msg = f'Load: {fpath}: {type(e).__name__}: {e}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCError(err_msg) from e
    except (jj2.TemplateError,) + cr_exc.JSON_ERRORS as e:
        err_msg = f'Load: {fpath}: {type(e).__name__}: {e}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCInvalidError(err_msg) from e
    else:
        return j_body


def rc_load_ini(fpath, emheading=None, render=False, **context):
    """Load INI-formatted data from a resource file. Content of a resource
    file can be pre-processed by Jinja2 rendering engine before being passed to
    INI-parser.

    :param fpath:     pathlib.Path, path to a source file
    :param emheading: str, heading to be added to the exception's description
    :param render:    bool, perform template rendering
    :param context:   dict, rendering context for jinja2.Temlate.render()
    :return:          dict, configparser.ConfigParser.read_dict() compatible
                      data.
    """
    assert isinstance(fpath, Path) and fpath.is_absolute(), (
        f'Argument: fpath: Absolute pathlib.Path is required: {fpath}'
    )

    cfg_parser = cfp.ConfigParser()

    try:
        if render is True:
            jj2_env = jj2.Environment(
                loader=jj2.FileSystemLoader(str(fpath.parent))
            )
            jj2_tmpl = jj2_env.get_template(str(fpath.name))
            ini_str = jj2_tmpl.render(**context)
            LOG.debug(f'rc_load_ini(): ini_str: {ini_str}')
            cfg_parser.read_string(ini_str, source=str(fpath))
        else:
            with fpath.open() as fp:
                cfg_parser.read_file(fp)
    except (FileNotFoundError, jj2.TemplateNotFound) as e:
        err_msg = f'Load: {fpath}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCNotFoundError(err_msg) from e
    except (OSError, RuntimeError) as e:
        err_msg = f'Load: {fpath}: {type(e).__name__}: {e}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCError(err_msg) from e
    except (jj2.TemplateError, cfp.Error) as e:
        err_msg = f'Load: {fpath}: {type(e).__name__}: {e}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCInvalidError(err_msg) from e
    else:
        return {k: dict(v) for k, v in cfg_parser.items()}


def rc_load_yaml(fpath, emheading=None, render=False, **context):
    """Load YAML-formatted data from a resource file. Content of a resource
    file can be pre-processed by Jinja2 rendering engine before being passed to
    YAML-parser.

    :param fpath:     pathlib.Path, path to a source file.
    :param emheading: str, heading to be added to the exception's description
    :param render:    bool, perform template rendering
    :param context:   dict, rendering context for jinja2.Temlate.render()
    :return:          yaml obj, YAML-formatted data
    """
    assert isinstance(fpath, Path) and fpath.is_absolute(), (
        f'Argument: fpath: Absolute pathlib.Path is required: {fpath}'
    )

    try:
        if render is True:
            jj2_env = jj2.Environment(
                loader=jj2.FileSystemLoader(str(fpath.parent))
            )
            jj2_tmpl = jj2_env.get_template(str(fpath.name))
            yaml_str = jj2_tmpl.render(**context)
            LOG.debug(f'rc_load_yaml(): yaml_str: {yaml_str}')
            y_body = yaml.safe_load(yaml_str)
        else:
            with fpath.open() as fp:
                y_body = yaml.safe_load(fp)
    except (FileNotFoundError, jj2.TemplateNotFound) as e:
        err_msg = f'Load: {fpath}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCNotFoundError(err_msg) from e
    except (OSError, RuntimeError) as e:
        err_msg = f'Load: {fpath}: {type(e).__name__}: {e}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCError(err_msg) from e
    except (jj2.TemplateError, yaml.YAMLError) as e:
        err_msg = f'Load: {fpath}: {type(e).__name__}: {e}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCInvalidError(err_msg) from e
    else:
        return y_body
