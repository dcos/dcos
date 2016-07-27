import json
import logging
import os
import subprocess
import sys

import gen
import pkgpanda
import gen.installer.bash
from dcos_installer.util import ARTIFACT_DIR, SERVE_DIR

log = logging.getLogger(__name__)


def do_configure(gen_config):
    gen_config.update(get_gen_extra_args())

    subprocess.check_output(['mkdir', '-p', SERVE_DIR])

    do_validate_gen_config(gen_config)

    gen_out = gen.generate(arguments=gen_config)
    gen.installer.bash.generate(gen_out, SERVE_DIR)

    # Get bootstrap from artifacts
    fetch_bootstrap(ARTIFACT_DIR, SERVE_DIR, gen_out.arguments['bootstrap_id'])
    # Get packages from artifacts
    fetch_packages(ARTIFACT_DIR, SERVE_DIR)
    # Write some package metadata
    pkgpanda.write_json('/genconf/cluster_packages.json', gen_out.cluster_packages)


def get_gen_extra_args():
    if 'BOOTSTRAP_ID' not in os.environ:
        log.error("BOOTSTRAP_ID must be set in environment to run.")
        raise KeyError

    # Get package IDs for this build from build metadata.
    try:
        package_ids = pkgpanda.util.load_json(os.path.join(ARTIFACT_DIR, 'complete.json'))['packages']
    except IOError as exc:
        message = "Can't find build metadata in artifacts."
        log.error(message)
        raise Exception(message) from exc
    except ValueError as exc:
        message = "Can't read build metadata."
        log.error(message)
        raise Exception(message) from exc

    arguments = {
        'bootstrap_id': os.environ['BOOTSTRAP_ID'],
        'package_ids': json.dumps(package_ids),
        'provider': 'onprem'}
    return arguments


def do_validate_gen_config(gen_config):
    # run validate first as this is the only way we have for now to remove "optional" keys
    gen_config.update(get_gen_extra_args())
    return gen.validate(arguments=gen_config)


def fetch_bootstrap(artifact_dir, dest_dir, bootstrap_id):
    copy_set = [
        "{}.bootstrap.tar.xz".format(bootstrap_id),
        "{}.active.json".format(bootstrap_id)]
    dest_dir = os.path.join(dest_dir, 'bootstrap')

    # If all the targets already exist, no-op
    dest_files = [os.path.join(dest_dir, filename) for filename in copy_set]
    if all(map(os.path.exists, dest_files)):
        return

    # Make sure the artifact files exist
    src_files = [os.path.join(artifact_dir, filename) for filename in copy_set]
    for filename in src_files:
        if not os.path.exists(filename):
            log.error("Internal Error: %s not found. Should have been in the installer container.", filename)
            raise FileNotFoundError()

    def cleanup_and_exit():
        for filename in dest_files:
            try:
                os.remove(filename)
            except OSError as ex:
                log.error("Internal error removing temporary file. Might have corrupted file %s: %s",
                          filename, ex.strerror)
        sys.exit(1)

    # Copy out the files, rolling back if it fails
    try:
        subprocess.check_output(['mkdir', '-p', dest_dir])

        # Copy across
        for filename in copy_set:
            subprocess.check_output(['cp', os.path.join(artifact_dir, filename), os.path.join(dest_dir, filename)])
    except subprocess.CalledProcessError as ex:
        log.error("Copy failed: %s\nOutput:\n%s", ex.cmd, ex.output)
        log.error("Removing partial artifacts")
        cleanup_and_exit()
    except KeyboardInterrupt:
        log.error("Copy out of installer interrupted. Removing partial files.")
        cleanup_and_exit()


def fetch_packages(artifact_dir, dest_dir):
    subprocess.check_call(['cp', '-R', os.path.join(artifact_dir, 'packages'), dest_dir])
