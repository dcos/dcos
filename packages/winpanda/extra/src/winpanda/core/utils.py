"""Panda package management for Windows.

Core utility routine definitions.
"""
import configparser as cfp
import json
from pathlib import Path

from core import exceptions as cr_exc


def rc_load_json(fpath, emheading=None):
    """Load JSON-formatted data from a (resource) file.

    :param fpath:     pathlib.Path, path to a source file.
    :param emheading: str, heading to be added to the exception's description
    :return:          json obj, JSON-formatted data
    """
    assert isinstance(fpath, Path) and fpath.is_absolute(), (
        f'Argument: fpath: Absolute pathlib.Path is required: {fpath}'
    )

    try:
        with fpath.open() as fp:
            j_body = json.load(fp, strict=False)
    except FileNotFoundError:
        err_msg = f'Load: {fpath}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCNotFoundError(err_msg)
    except (OSError, RuntimeError) as e:
        err_msg = f'Load: {fpath}: {type(e).__name__}: {e}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCError(err_msg)
    except cr_exc.JSON_ERRORS as e:
        err_msg = f'Load: {fpath}: {type(e).__name__}: {e}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCInvalidError(err_msg)
    else:
        return j_body


def rc_load_ini(fpath, emheading=None):
    """Load INI-formatted data from a (resource) file.

    :param fpath:     pathlib.Path, path to a source file
    :param emheading: str, heading to be added to the exception's description
    :return:          dict, configparser.ConfigParser.read_dict() compatible
                      data.
    """
    assert isinstance(fpath, Path) and fpath.is_absolute(), (
        f'Argument: fpath: Absolute pathlib.Path is required: {fpath}'
    )

    cfg_parser = cfp.ConfigParser()

    try:
        with fpath.open() as fp:
            cfg_parser.read_file(fp)
    except FileNotFoundError:
        err_msg = f'Load: {fpath}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCNotFoundError(err_msg)
    except (OSError, RuntimeError) as e:
        err_msg = f'Load: {fpath}: {type(e).__name__}: {e}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCError(err_msg)
    except cfp.Error as e:
        err_msg = f'Load: {fpath}: {type(e).__name__}: {e}'
        err_msg = f'{emheading}: {err_msg}' if emheading else err_msg
        raise cr_exc.RCInvalidError(err_msg)
    else:
        return {k: dict(v) for k, v in cfg_parser.items()}
