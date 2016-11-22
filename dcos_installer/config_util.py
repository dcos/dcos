import logging
import os
import subprocess
import sys

import gen
import gen.build_deploy.bash
import pkgpanda
from dcos_installer.constants import BOOTSTRAP_DIR, CLUSTER_PACKAGES_PATH, SERVE_DIR

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


def do_configure(config):
    gen_out = onprem_generate(config)
    make_serve_dir(gen_out)


def do_move_atomic(src_dir, dest_dir, filenames):
    assert os.path.exists(src_dir)
    assert os.path.exists(dest_dir)

    def rollback():
        for filename in filenames:
            filename = dest_dir + '/' + filename
            try:
                os.remove(filename)
            except OSError as ex:
                log.error("Internal error removing temporary file. Might have corrupted file %s: %s",
                          filename, ex.strerror)
        sys.exit(1)

    try:
        # Copy across
        for filename in filenames:
            subprocess.check_output(['cp', src_dir + '/' + filename, dest_dir + '/' + filename])
    except subprocess.CalledProcessError as ex:
        log.error("Copy failed: %s\nOutput:\n%s", ex.cmd, ex.output)
        log.error("Removing partial artifacts")
        rollback()
    except KeyboardInterrupt:
        log.error("Copy out of installer interrupted. Removing partial files.")
        rollback()


def fetch_bootstrap(bootstrap_id):
    filenames = [
        "{}.bootstrap.tar.xz".format(bootstrap_id),
        "{}.active.json".format(bootstrap_id)]
    container_cache_dir = "artifacts/bootstrap"

    # If all the targets already exist, no-op
    dest_files = [BOOTSTRAP_DIR + '/' + filename for filename in filenames]
    if all(map(os.path.exists, dest_files)):
        return

    # Make sure the internal cache files exist
    src_files = [container_cache_dir + '/' + filename for filename in filenames]
    for filename in src_files:
        if not os.path.exists(filename):
            log.error("Internal Error: %s not found. Should have been in the installer container.", filename)
            raise FileNotFoundError(filename)

    subprocess.check_call(['mkdir', '-p', BOOTSTRAP_DIR])
    do_move_atomic(container_cache_dir, BOOTSTRAP_DIR, filenames)
