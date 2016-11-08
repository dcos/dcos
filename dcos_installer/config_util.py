import logging
import os
import subprocess
import sys

import gen
import gen.installer.aws
import gen.installer.bash
import pkgpanda
from dcos_installer.constants import GENCONF_DIR, GENERATED_CONFIG_DIR, SERVE_DIR


log = logging.getLogger(__name__)


def do_configure(config, updating_config=False):
    gen_out = config.do_gen_configure()

    config_id = gen_out.arguments['config_id']
    config_id_dir = GENERATED_CONFIG_DIR + config_id + '/serve'
    output_dir = config_id_dir if updating_config else SERVE_DIR
    bootstrap_dir = output_dir + '/bootstrap'

    subprocess.check_call(['mkdir', '-p', output_dir])
    gen.installer.bash.generate(gen_out, output_dir)

    # Get bootstrap from artifacts
    # TODO(cmaloney): Switch to use a local storage provider like do_aws_configure does.
    fetch_bootstrap(gen_out.arguments['bootstrap_id'], bootstrap_dir)
    # Write some package metadata
    base_dir = GENERATED_CONFIG_DIR + config_id if updating_config else GENCONF_DIR
    pkgpanda.util.write_json(base_dir + '/cluster_packages.json', gen_out.cluster_packages)


def do_move_atomic(src_dir, dest_dir, filenames):
    assert os.path.exists(src_dir)
    assert os.path.exists(dest_dir)

    def rollback():
        for filename in filenames:
            filename = dest_dir + filename
            try:
                os.remove(filename)
            except OSError as ex:
                log.error("Internal error removing temporary file. Might have corrupted file %s: %s",
                          filename, ex.strerror)
        sys.exit(1)

    try:
        # Copy across
        for filename in filenames:
            subprocess.check_output(['cp', src_dir + filename, dest_dir + filename])
    except subprocess.CalledProcessError as ex:
        log.error("Copy failed: %s\nOutput:\n%s", ex.cmd, ex.output)
        log.error("Removing partial artifacts")
        rollback()
    except KeyboardInterrupt:
        log.error("Copy out of installer interrupted. Removing partial files.")
        rollback()


def fetch_bootstrap(bootstrap_id, dest_dir):
    filenames = [
        "{}.bootstrap.tar.xz".format(bootstrap_id),
        "{}.active.json".format(bootstrap_id)]
    container_cache_dir = "artifacts/bootstrap/"

    # If all the targets already exist, no-op
    dest_files = [dest_dir + filename for filename in filenames]
    if all(map(os.path.exists, dest_files)):
        return

    # Make sure the internal cache files exist
    src_files = [container_cache_dir + filename for filename in filenames]
    for filename in src_files:
        if not os.path.exists(filename):
            log.error("Internal Error: %s not found. Should have been in the installer container.", filename)
            raise FileNotFoundError(filename)

    subprocess.check_call(['mkdir', '-p', dest_dir])
    do_move_atomic(container_cache_dir, dest_dir, filenames)
