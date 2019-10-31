"""Panda package management for Windows.

Core utility routine definitions.
"""
import configparser as cfp
import io
import json
from pathlib import Path
import re

from common import logger
from core import exceptions as cr_exc


LOG = logger.get_logger(__name__)


def rc_load_json(fpath, emheading=None):
    """Load JSON-formatted data from a (resource) file.

    :param fpath:     pathlib.Path, path to a source file.
    :param emheading: str, heading to be added to the exception's description
    :return:          json obj, JSON-formatted data
    """
    assert isinstance(fpath, Path) and fpath.is_absolute(), (
        f'Argument: fpath: Absolute pathlib.Path is required: {fpath}'
    )

    # In-memory string buffer
    str_buf = io.StringIO()
    # Backspace combination lookup pattern.
    # bs_pair  - a pair of backspace characters - not to be screened
    # bs_quote - backspace + (double) quote character- not to be screened
    # bs_alpha - backspace + alphabetic character - to be screened
    bs_pattern = (
        r'(?P<bs_pair>\\{2})|(?P<bs_quote>\\["\'])|(?P<bs_alpha>\\[a-z])'
    )

    try:
        # Screen 'bs_alpha' combinations to eliminate interpreting
        # parts of 'raw' lines as escape sequences.
        with fpath.open() as fp:
            for r_line in fp:
                # Discover positions of backspace combinations to screen
                s_pos = []
                for match in re.finditer(bs_pattern, r_line):
                    if match.group('bs_alpha'):
                        s_pos.append(match.start())
                # Accept a 'raw' string, if no screening is required
                if not s_pos:
                    str_buf.write(r_line)
                    continue
                # Compose the 'head' of 'screened' line
                s_line_parts = [r_line[:s_pos[0]]]
                # Compose the 'body' of 'screened' line
                for i in range(len(s_pos) - 1):
                    s_line_parts.append(
                        r_line[s_pos[i]:s_pos[i + 1]]
                    )
                # Compose the 'tail' of 'screened' line
                s_line_parts.append(r_line[s_pos[-1]:])
                # Glue parts together
                s_line = '\\'.join(s_line_parts)
                # Save a 'screened' line
                str_buf.write(s_line)
        # Parse collected strings
        str_buf_data = str_buf.getvalue()
        LOG.debug(f'rc_load_json(): str_buf: {str_buf_data}')
        j_body = json.loads(str_buf_data)
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
