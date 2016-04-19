import json
import os
import re
import shutil
from itertools import chain
from shutil import rmtree, which
from subprocess import check_call, check_output

import requests

from pkgpanda.exceptions import FetchError, ValidationError


def variant_str(variant):
    """Return a string representation of variant."""
    if variant is None:
        return ''
    return variant


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


def download(out_filename, url, work_dir):
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
                r = requests.get(url, stream=True)
                if r.status_code == 301:
                    raise Exception("got a 301")
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=4096):
                    f.write(chunk)
    except Exception as fetch_exception:
        rm_passed = False

        # try / except so if remove fails we don't get an exception during an exception.
        # Sets rm_passed to true so if this fails we can include a special error message in the
        # FetchError
        try:
            os.remove(out_filename)
            rm_passed = True
        except Exception:
            pass

        raise FetchError(url, out_filename, fetch_exception, rm_passed) from fetch_exception


def extract_tarball(path, target):
    """Extract the tarball into target.

    If there are any errors, delete the folder being extracted to.
    """
    # TODO(cmaloney): Validate extraction will pass before unpacking as much as possible.
    # TODO(cmaloney): Unpack into a temporary directory then move into place to
    # prevent partial extraction from ever laying around on the filesystem.
    try:
        assert os.path.exists(path)
        check_call(['mkdir', '-p', target])
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


def make_file(name):
    with open(name, 'a'):
        pass


def write_json(filename, data):
    with open(filename, "w+") as f:
        return json.dump(data, f, indent=2, sort_keys=True)


def write_string(filename, data):
    with open(filename, "w+") as f:
        return f.write(data)


def load_string(filename):
    with open(filename) as f:
        return f.read().strip()


def if_exists(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except FileNotFoundError:
        return None


def sha1(filename):
    return check_output(["sha1sum", filename]).split()[0].decode('ascii')


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
    tar_cmd = ["tar", "--numeric-owner", "--owner=0", "--group=0"]
    if which("pxz"):
        tar_cmd += ["--use-compress-program=pxz", "-cf"]
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
                    new_target = os.path.join(new_prefix, target[len(old_prefix)+1:].lstrip('/'))
                    # Remove the old link and write a new one.
                    os.remove(full_path)
                    os.symlink(new_target, full_path)


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
