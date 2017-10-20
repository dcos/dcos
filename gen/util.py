import logging
import os
import os.path

from tempfile import TemporaryDirectory

from pkgpanda.util import make_tar


def pkgpanda_package_tmpdir():
    # Forcibly set umask so that os.makedirs() always makes directories with
    # uniform permissions
    os.umask(0o000)
    return TemporaryDirectory("gen_tmp_pkg")


def make_pkgpanda_package(contents_dir, package_filename):
    # Make the package top level directory readable by users other than the owner (root).
    os.chmod(contents_dir, 0o755)

    # Ensure the output directory exists
    if os.path.dirname(package_filename):
        os.makedirs(os.path.dirname(package_filename), exist_ok=True)

    make_tar(package_filename, contents_dir)
    logging.info("Package filename: %s", package_filename)
