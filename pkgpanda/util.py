import ctypes
import hashlib
import http.server
import json
import logging
import os
import platform
import re
import shutil
import socketserver
import stat
import subprocess
import tempfile
from contextlib import contextmanager, ExitStack
from itertools import chain
from multiprocessing import Process
from shutil import rmtree, which
from subprocess import check_call
from time import sleep
from typing import List

import requests
import teamcity
import yaml
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from teamcity.messages import TeamcityServiceMessages

from pkgpanda.exceptions import FetchError, ValidationError


is_windows = platform.system() == "Windows"


def is_absolute_path(path):
    if is_windows:
        # We assume one char drive letter. Sometimes its two but not often
        # pattern is <driveletter>:/string....
        if path[1] == ':':
            return True
    else:
        if path[0] == '/':
            return True
    return False


def remove_file(path):
    """removes a file. fails silently if the file does not exist"""
    if is_windows:
        # python library on Windows does not like symbolic links in directories
        # so calling out to the cmd prompt to do this fixes that.
        path = path.replace('/', '\\')
        if os.path.exists(path):
            subprocess.call(['cmd.exe', '/c', 'del', '/q', path])
    else:
        subprocess.check_call(['rm', '-f', path])


def remove_directory(path):
    """recursively removes a directory tree. fails silently if the tree does not exist"""
    if is_windows:
        # python library on Windows does not like symbolic links in directories
        # so calling out to the cmd prompt to do this fixes that.
        path = path.replace('/', '\\')
        if os.path.exists(path):
            for retry in range(1, 10):
                try:
                    subprocess.check_call(['cmd.exe', '/c', 'rmdir', '/s', '/q', path], stdout=subprocess.DEVNULL)
                except subprocess.CalledProcessError:
                    if retry == 10:
                        raise
                    else:
                        sleep(0.05)
                        continue
                break
    else:
        subprocess.check_call(['rm', '-rf', path])


def rename_file(src, dst):
    """Rename a file or directory"""
    if is_windows:
        for retry in range(1, 10):
            try:
                os.rename(src, dst)
            except PermissionError:
                if retry == 10:
                    raise
                else:
                    sleep(0.05)
                    continue
            break
    else:
        os.rename(src, dst)


def make_directory(path):
    """Create a directory, creating intermediate directories if necessary"""
    if is_windows:
        path = path.replace('/', '\\')

    if not os.path.exists(path):
        os.makedirs(path)


def copy_file(src_path, dst_path):
    """copy a single directory item from one location to another"""
    if is_windows:
        # To make sure the copy works we are using cmd version as python
        # libraries may not handle symbolic links and other things that are
        # thrown at it.
        src = src_path.replace('/', '\\')
        dst = dst_path.replace('/', '\\')
        subprocess.check_call(['cmd.exe', '/c', 'copy', src, dst])
    else:
        subprocess.check_call(['cp', src_path, dst_path])


def copy_directory(src_path, dst_path):
    """copy recursively a directory tree from one location to another"""
    if is_windows:
        # To make sure the copy works we are using cmd version as python
        # libraries may not handle symbolic links and other things that are
        # thrown at it.
        src = src_path.replace('/', '\\')
        dst = dst_path.replace('/', '\\')
        subprocess.check_call(['cmd.exe', '/c', 'xcopy', src, dst, '/E', '/B', '/I'])
    else:
        subprocess.check_call(['cp', '-r', src_path, dst_path])


def link_file(src, dst):
    """Create file links in an OS independent manner.

    On Linux, this will create symbolic links for both files and directories.
    On Windows, this will create hard links for files, and junctions (a.k.a symbolic links) for directories.

    """
    if is_windows:
        if os.path.isdir(src):
            # create a junction for directories
            src = src.replace('/', '\\')
            dst = dst.replace('/', '\\')
            subprocess.check_call(['cmd.exe', '/c', 'mklink', '/J', dst, src], stdout=subprocess.DEVNULL)
        else:
            # create hard link for files
            os.link(src, dst)

    else:
        os.symlink(src, dst)


def _is_junction(path):
    if not is_windows:
        raise Exception("Calls to _is_junction() only supported on Windows")

    # TODO(klueska): Investigate why we need this 'isdir()' check. As far as I
    # can tell, the check below that relies on 'GetFileAttributesW()' will
    # return 'True' in cases where the 'path' passed to it is a symbolic link for
    # either a _file_ or a _directory_. Since a 'junction' is only a directory
    # level concept, its possible that the 'isdir()' check is required to limit
    # us to directories only, before we ever make the call to
    # 'GetFileAttributesW()'. This should be confirmed though.
    if not os.path.isdir(path):
        return False

    file_attribute_reparse_point = 0x0400
    attributes = ctypes.windll.kernel32.GetFileAttributesW(path)
    return (attributes & file_attribute_reparse_point) > 0


def islink(path):
    """Check if a file is a link to another file in an OS independent manner.

    On Linux, this will check for symbolic links for both files and directories.
    On Windows, this will check for hard links for files, and junctions (a.k.a symbolic links) for directories.

    """
    if is_windows:
        if os.path.isdir(path):
            return _is_junction(path)
        elif os.stat(path).st_nlink > 1:
            return True
        else:
            return False
    else:
        return os.path.islink(path)


def realpath(path):
    """Get the realpath of 'path' in an OS independent manner (following links as necessary)."""
    if is_windows:
        if os.path.exists(path) and islink(path):
            # if 'path' is a link, call powershell to get the target of the link
            return subprocess.check_output(["powershell", "(get-item " + path + ").target"]).decode().splitlines()[0]
        else:
            # regular file so let os.path do its thing
            return os.path.realpath(path)
    else:
        return os.path.realpath(path)


def variant_str(variant):
    """Return a string representation of variant."""
    if variant is None:
        return ''
    return variant


def variant_object(variant_str):
    """Return a variant object from its string representation."""
    if variant_str == '':
        return None
    return variant_str


def variant_name(variant):
    """Return a human-readable string representation of variant."""
    if variant is None:
        return '<default>'
    return variant


def variant_prefix(variant):
    """Return a filename prefix for variant."""
    if variant is None:
        return ''
    return variant + '.'


def variant_suffix(variant, delim='.'):
    if variant is None:
        return ''
    return delim + variant


def get_requests_retry_session(max_retries=4, backoff_factor=1, status_forcelist=None):
    status_forcelist = status_forcelist or [500, 502, 504]
    # Default max retries 4 with sleeping between retries 1s, 2s, 4s, 8s
    session = requests.Session()
    custom_retry = Retry(total=max_retries,
                         backoff_factor=backoff_factor,
                         status_forcelist=status_forcelist)
    custom_adapter = HTTPAdapter(max_retries=custom_retry)
    # Any request through this session that starts with 'http://' or 'https://'
    # will use the custom Transport Adapter created which include retries
    session.mount('http://', custom_adapter)
    session.mount('https://', custom_adapter)
    return session


def download(out_filename, url, work_dir, rm_on_error=True):
    assert os.path.isabs(out_filename)
    assert os.path.isabs(work_dir)
    work_dir = work_dir.rstrip('/')

    # Strip off whitespace to make it so scheme matching doesn't fail because
    # of simple user whitespace.
    url = url.strip()

    # Handle file:// urls specially since requests doesn't know about them.
    try:
        if url.startswith('file://'):
            src_filename = url[len('file://'):]
            if not os.path.isabs(src_filename):
                src_filename = work_dir + '/' + src_filename
            shutil.copyfile(src_filename, out_filename)
        else:
            # Download the file.
            with open(out_filename, "w+b") as f:
                r = get_requests_retry_session().get(url, stream=True)
                if r.status_code == 301:
                    raise Exception("got a 301")
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=4096):
                    f.write(chunk)
    except Exception as fetch_exception:
        if rm_on_error:
            rm_passed = False

            # try / except so if remove fails we don't get an exception during an exception.
            # Sets rm_passed to true so if this fails we can include a special error message in the
            # FetchError
            try:
                os.remove(out_filename)
                rm_passed = True
            except Exception:
                pass
        else:
            rm_passed = True

        raise FetchError(url, out_filename, fetch_exception, rm_passed) from fetch_exception


def download_atomic(out_filename, url, work_dir):
    assert os.path.isabs(out_filename)
    tmp_filename = out_filename + '.tmp'
    try:
        download(tmp_filename, url, work_dir)
        os.rename(tmp_filename, out_filename)
    except FetchError:
        try:
            os.remove(tmp_filename)
        except:
            pass
        raise


def extract_tarball(path, target):
    """Extract the tarball into target.

    If there are any errors, delete the folder being extracted to.
    """
    # TODO(cmaloney): Validate extraction will pass before unpacking as much as possible.
    # TODO(cmaloney): Unpack into a temporary directory then move into place to
    # prevent partial extraction from ever laying around on the filesystem.
    try:
        assert os.path.exists(path), "Path doesn't exist but should: {}".format(path)
        make_directory(target)

        if is_windows:
            check_call(['bsdtar', '-xf', path, '-C', target])
        else:
            check_call(['tar', '-xf', path, '-C', target])

    except:
        # If there are errors, we can't really cope since we are already in an error state.
        rmtree(target, ignore_errors=True)
        raise


def load_json(filename):
    try:
        with open(filename) as f:
            return json.load(f)
    except ValueError as ex:
        raise ValueError("Invalid JSON in {0}: {1}".format(filename, ex)) from ex


class YamlParseError(Exception):
    pass


def load_yaml(filename):
    try:
        with open(filename) as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as ex:
        raise YamlParseError("Invalid YAML in {}: {}".format(filename, ex)) from ex


def write_yaml(filename, data, **kwargs):
    dumped_yaml = yaml.safe_dump(data, **kwargs)
    write_string(filename, dumped_yaml)


def make_file(name):
    with open(name, 'a'):
        pass


def write_json(filename, data):
    dumped_json = json_prettyprint(data=data)
    write_string(filename, dumped_json)


def write_string(filename, data):
    """
    Write a string to a file.
    Overwrite any data in that file.

    We use an atomic write practice of creating a temporary file and then
    moving that temporary file to the given ``filename``. This prevents race
    conditions such as the file being read by another process after it is
    opened here but not yet written to.

    It also prevents us from creating or truncating a file before we fail to
    write data to it because of low disk space.

    If no file already exists at ``filename``, the new file is created with
    permissions 0o644.
    """
    prefix = os.path.basename(filename)
    tmp_file_dir = os.path.dirname(realpath(filename))
    fd, temporary_filename = tempfile.mkstemp(prefix=prefix, dir=tmp_file_dir)

    try:
        permissions = os.stat(filename).st_mode
    except FileNotFoundError:
        permissions = 0o644

    try:
        try:
            os.write(fd, data.encode())
        finally:
            os.close(fd)
        os.chmod(temporary_filename, stat.S_IMODE(permissions))
        os.replace(temporary_filename, filename)
    except Exception:
        os.remove(temporary_filename)
        raise


def load_string(filename):
    with open(filename) as f:
        return f.read().strip()


def json_prettyprint(data):
    return json.dumps(
        data,
        sort_keys=True,
        indent=2,
        separators=(',', ':'),
    )


def if_exists(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except FileNotFoundError:
        return None


def sha1(filename):
    hasher = hashlib.sha1()

    with open(filename, 'rb') as fh:
        while 1:
            buf = fh.read(4096)
            if not buf:
                break
            hasher.update(buf)

    return hasher.hexdigest()


def expect_folder(path, files):
    path_contents = os.listdir(path)
    assert set(path_contents) == set(files)


def expect_fs(folder, contents):
    if isinstance(contents, list):
        expect_folder(folder, contents)
    elif isinstance(contents, dict):
        expect_folder(folder, contents.keys())

        for path in iter(contents):
            if contents[path] is not None:
                expect_fs(os.path.join(folder, path), contents[path])
    else:
        raise ValueError("Invalid type {0} passed to expect_fs".format(type(contents)))


def make_tar(result_filename, change_folder):
    if is_windows:
        tar_cmd = ["bsdtar"]
    else:
        tar_cmd = ["tar", "--numeric-owner", "--owner=0", "--group=0"]
    if which("pxz"):
        tar_cmd += ["--use-compress-program=pxz", "-cf"]
    else:
        if is_windows:
            tar_cmd += ["-cjf"]
        else:
            tar_cmd += ["-cJf"]
    tar_cmd += [result_filename, "-C", change_folder, "."]
    check_call(tar_cmd)


def rewrite_symlinks(root, old_prefix, new_prefix):
    # Find the symlinks and rewrite them from old_prefix to new_prefix
    # All symlinks not beginning with old_prefix are ignored because
    # packages may contain arbitrary symlinks.
    for root_dir, dirs, files in os.walk(root):
        for name in chain(files, dirs):
            full_path = os.path.join(root_dir, name)
            if os.path.islink(full_path):
                # Rewrite old_prefix to new_prefix if present.
                target = os.readlink(full_path)
                if target.startswith(old_prefix):
                    new_target = os.path.join(new_prefix, target[len(old_prefix) + 1:].lstrip('/'))
                    # Remove the old link and write a new one.
                    os.remove(full_path)
                    link_file(new_target, full_path)


def check_forbidden_services(path, services):
    """Check if package contains systemd services that may break DC/OS

    This functions checks the contents of systemd's unit file dirs and
    throws the exception if there are reserved services inside.

    Args:
        path: path where the package contents are
        services: list of reserved services to look for

    Raises:
        ValidationError: Reserved serice names were found inside the package
    """
    services_dir_regexp = re.compile(r'dcos.target.wants(?:_.+)?')
    forbidden_srv_set = set(services)
    pkg_srv_set = set()

    for direntry in os.listdir(path):
        if not services_dir_regexp.match(direntry):
            continue
        pkg_srv_set.update(set(os.listdir(os.path.join(path, direntry))))

    found_units = forbidden_srv_set.intersection(pkg_srv_set)

    if found_units:
        msg = "Reverved unit names found: " + ','.join(found_units)
        raise ValidationError(msg)


def run(cmd, *args, **kwargs):
    proc = subprocess.Popen(
        cmd,
        *args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        **kwargs)
    stdout, stderr = proc.communicate()
    print("STDOUT: ", stdout)
    print("STDERR: ", stderr)

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)

    assert len(stderr) == 0
    return stdout


def launch_server(directory):
    os.chdir("resources/repo")
    httpd = socketserver.TCPServer(
        ("", 8000),
        http.server.SimpleHTTPRequestHandler)
    httpd.serve_forever()


class TestRepo:

    def __init__(self, repo_dir):
        self.__dir = repo_dir

    def __enter__(self):
        self.__server = Process(target=launch_server, args=(self.__dir))
        self.__server.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self.__server.join()


def resources_test_dir(path):
    assert not path.startswith('/')
    if is_windows:
        return "pkgpanda/test_resources/windows/{}".format(path)
    return "pkgpanda/test_resources/unix/{}".format(path)


class MessageLogger:
    """Abstraction over TeamCity Build Messages

    When pkgpanda is ran in a TeamCity environment additional meta-messages will be output to stdout
    such that TeamCity can provide improved status reporting, log line highlighting, and failure
    reporting. When pkgpanda is ran in an environment other than TeamCity all meta-messages will
    silently be omitted.

    TeamCity docs: https://confluence.jetbrains.com/display/TCD10/Build+Script+Interaction+with+TeamCity
    """
    def __init__(self):
        self.loggers = []
        if teamcity.is_running_under_teamcity():
            self.loggers.append(TeamcityServiceMessages())
        else:
            self.loggers.append(PrintLogger())

    def _custom_message(self, text, status, error_details='', flow_id=None):
        for log in self.loggers:
            log.customMessage(text, status, errorDetails=error_details, flowId=flow_id)

    @contextmanager
    def _block(self, log, name, flow_id):
        log.blockOpened(name, flowId=flow_id)
        log.progressMessage(name)
        yield
        log.blockClosed(name, flowId=flow_id)

    @contextmanager
    def scope(self, name, flow_id=None):
        """
        Creates a new scope for TeamCity messages. This method is intended to be called in a ``with`` statement

        :param name: The name of the scope
        :param flow_id: Optional flow id that can be used if ``name`` can be non-unique
        """
        with ExitStack() as stack:
            for log in self.loggers:
                stack.enter_context(self._block(log, name, flow_id))
            yield

    def normal(self, text, flow_id=None):
        self._custom_message(text=text, status='NORMAL', flow_id=flow_id)

    def warning(self, text, flow_id=None):
        self._custom_message(text=text, status='WARNING', flow_id=flow_id)

    def error(self, text, flow_id=None, error_details=''):
        self._custom_message(text=text, status='ERROR', flow_id=flow_id, error_details=error_details)

    def failure(self, text, flow_id=None):
        self._custom_message(text=text, status='FAILURE', flow_id=flow_id)


class PrintLogger:
    def customMessage(self, text, status, errorDetails='', flowId=None):  # noqa: N802, N803
        print("{}: {} {}".format(status, text, errorDetails))

    def progressMessage(self, message):  # noqa: N802, N803
        pass

    def blockOpened(self, name, flowId=None):  # noqa: N802, N803
        print("starting: {}".format(name))

    def blockClosed(self, name, flowId=None):  # noqa: N802, N803
        print("completed: {}".format(name))


logger = MessageLogger()


def hash_str(s: str):
    hasher = hashlib.sha1()
    hasher.update(s.encode('utf-8'))
    return hasher.hexdigest()


def hash_int(i: int):
    return hash_str(str(i))


def hash_dict(d: dict):
    item_hashes = []
    for k in sorted(d.keys()):
        assert isinstance(k, str)
        item_hashes.append("{0}={1}".format(k, hash_checkout(d[k])))
    return hash_str(",".join(item_hashes))


def hash_list(l: List[str]):
    item_hashes = []
    for item in sorted(l):
        item_hashes.append(hash_checkout(item))
    return hash_str(",".join(item_hashes))


def hash_checkout(item):

    if isinstance(item, str) or isinstance(item, bytes):
        return hash_str(item)
    elif isinstance(item, dict):
        return hash_dict(item)
    elif isinstance(item, list):
        return hash_list(item)
    elif isinstance(item, int):
        return hash_int(item)
    elif isinstance(item, set):
        return hash_list(list(item))
    else:
        raise NotImplementedError("{} of type {}".format(item, type(item)))


def split_by_token(token_prefix, token_suffix, string_, strip_token_decoration=False):
    """Yield a sequence of (substring, is_token) pairs comprising the string.

    The string is split by token boundary, where a token is a substring that
    begins with the token prefix and ends with the token suffix. is_token is
    True if the substring is a token. If strip_token_decoration is True, tokens
    are yielded without their prefix and suffix. Each token prefix must have a
    matching suffix, and vice versa. Tokens may not be nested.

    >>> list(split_by_token('{', '}', 'some text {token} some more text'))
    [('some text ', False), ('{token}', True), (' some more text', False)]
    >>> list(split_by_token('{', '}', 'some text {token} some more text', strip_token_decoration=True))
    [('some text ', False), ('token', True), (' some more text', False)]

    """

    def _next_substring(superstring, substring, start):
        idx = superstring.find(substring, start)
        if idx < 0:
            return None
        return idx, idx + len(substring)

    def _raise_exception_if_suffix_in(substring):
        if token_suffix in substring:
            logging.debug("Token suffix found without matching prefix in string: {}".format(repr(string_)))
            raise Exception("Token suffix found without matching prefix")

    if len(token_prefix) == 0:
        raise ValueError('Token prefix must be a nonzero length string')
    if len(token_suffix) == 0:
        raise ValueError('Token suffix must be a nonzero length string')

    if string_ == '':
        yield string_, False

    num_chars_consumed = 0
    while num_chars_consumed < len(string_):
        # Find the next token.
        token_start = _next_substring(string_, token_prefix, num_chars_consumed)
        if not token_start:
            # No token found. Yield the rest of the string and return.
            remainder = string_[num_chars_consumed:]
            _raise_exception_if_suffix_in(remainder)
            yield remainder, False
            return

        # Yield the string preceding the token, if any.
        if token_start[0] > num_chars_consumed:
            preceding_string = string_[num_chars_consumed:token_start[0]]
            _raise_exception_if_suffix_in(preceding_string)
            yield preceding_string, False

        # Find the end of the token.
        token_end = _next_substring(string_, token_suffix, token_start[1])
        if not token_end or token_prefix in string_[token_start[1]:token_end[0]]:
            # Can't find a closing suffix, or found two consecutive prefixes without a suffix between them.
            logging.debug("Token prefix found without matching suffix in string: {}".format(repr(string_)))
            raise Exception("Token prefix found without matching suffix")

        # Yield the token.
        if strip_token_decoration:
            # Omit the token's prefix and suffix.
            yield string_[token_start[1]:token_end[0]], True
        else:
            # Yield the entire token.
            yield string_[token_start[0]:token_end[1]], True

        # Update the chars consumed count for the next iteration.
        num_chars_consumed = token_end[1]
