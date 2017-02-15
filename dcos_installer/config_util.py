import logging
import os
import subprocess
import sys

import gen
import gen.build_deploy.bash
import pkgpanda
from dcos_installer.constants import ARTIFACT_DIR, CLUSTER_PACKAGES_PATH, SERVE_DIR

log = logging.getLogger(__name__)


def onprem_generate(config):
    return gen.generate(config.as_gen_format(), extra_sources=[gen.build_deploy.bash.onprem_source])


def make_serve_dir(gen_out):
    subprocess.check_call(['mkdir', '-p', SERVE_DIR])
    gen.build_deploy.bash.generate(gen_out, SERVE_DIR)

    # Get bootstrap from artifacts
    fetch_bootstrap(gen_out.arguments['bootstrap_id'])
    # Write some package metadata
    pkgpanda.util.write_json(CLUSTER_PACKAGES_PATH, gen_out.cluster_packages)


def parent_dirs(filename):
    assert not (filename.startswith('/') or filename.endswith('/'))
    dirs = []
    for directory in filename.split('/')[:-1]:
        dirs.append(directory)
        yield '/'.join(dirs)


def do_configure(config):
    gen_out = onprem_generate(config)
    make_serve_dir(gen_out)


def do_move_atomic(src_dir, dest_dir, filenames):
    assert os.path.exists(src_dir)
    assert os.path.exists(dest_dir)

    created_dirs = []
    created_files = []

    def mkdir(dirname):
        created_dirs.append(dirname)
        subprocess.check_output(['mkdir', dirname])

    def copy(src, dest):
        created_files.append(dest)
        subprocess.check_output(['cp', src, dest])

    def rollback():
        for filename in reversed(created_files):
            try:
                os.remove(filename)
            except OSError as ex:
                log.error("Internal error removing temporary file. Might have corrupted file %s: %s",
                          filename, ex.strerror)

        for filename in reversed(created_dirs):
            try:
                os.rmdir(filename)
            except OSError as ex:
                log.error("Internal error removing temporary dir %s: %s", filename, ex.strerror)

        sys.exit(1)

    try:
        # Copy across
        for filename in filenames:
            for parent_dir in parent_dirs(filename):
                dest_parent_dir = dest_dir + '/' + parent_dir
                if not os.path.exists(dest_parent_dir):
                    mkdir(dest_parent_dir)
            copy(src_dir + '/' + filename, dest_dir + '/' + filename)
    except subprocess.CalledProcessError as ex:
        log.error("Copy failed: %s\nOutput:\n%s", ex.cmd, ex.output)
        log.error("Removing partial artifacts")
        rollback()
    except KeyboardInterrupt:
        log.error("Copy out of installer interrupted. Removing partial files.")
        rollback()


def fetch_artifacts(bootstrap_id, cluster_packages, config_package_ids):
    filenames = [
        "bootstrap/{}.bootstrap.tar.xz".format(bootstrap_id),
        "bootstrap/{}.active.json".format(bootstrap_id)
    ] + sorted(
        # Onprem config packages are created by genconf. They aren't available in the cache.
        info['filename'] for info in cluster_packages.values() if info['id'] not in config_package_ids
    )
    dest_dir = SERVE_DIR
    container_cache_dir = ARTIFACT_DIR

    # If all the targets already exist, no-op
    dest_files = [dest_dir + '/' + filename for filename in filenames]
    if all(map(os.path.exists, dest_files)):
        return

    # Make sure the internal cache files exist
    src_files = [container_cache_dir + '/' + filename for filename in filenames]
    for filename in src_files:
        if not os.path.exists(filename):
            log.error("Internal Error: %s not found. Should have been in the installer container.", filename)
            raise FileNotFoundError(filename)

    subprocess.check_call(['mkdir', '-p', dest_dir])
    do_move_atomic(container_cache_dir, dest_dir, filenames)


def installer_latest_complete_artifact(variant_str):
    return pkgpanda.util.load_json(
        ARTIFACT_DIR + '/complete/{}complete.latest.json'.format(
            pkgpanda.util.variant_prefix(pkgpanda.util.variant_object(variant_str)))
    )
