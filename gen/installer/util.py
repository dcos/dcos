import json
import os
import shutil
from datetime import datetime
from subprocess import check_output

from pkgpanda.util import write_json, write_string

dcos_image_commit = os.getenv('DCOS_IMAGE_COMMIT', None)

if dcos_image_commit is None:
    dcos_image_commit = check_output(['git', 'rev-parse', 'HEAD']).decode('utf-8').strip()

if dcos_image_commit is None:
    raise "Unable to set dcos_image_commit from teamcity or git."

template_generation_date = str(datetime.utcnow())


def try_makedirs(path):
    try:
        os.makedirs(path)
    except FileExistsError:
        pass


def copy_makedirs(src, dest):
    try_makedirs(os.path.dirname(dest))
    shutil.copy(src, dest)


def do_bundle_onprem(extra_files, gen_out, output_dir):
    # We are only being called via dcos_generate_config.sh with an output_dir
    assert output_dir is not None
    assert output_dir
    assert output_dir[-1] != '/'
    output_dir = output_dir + '/'

    # Copy the extra_files
    for filename in extra_files:
        shutil.copy(filename, output_dir + filename)

    # Copy the config packages
    for package_name in json.loads(gen_out.arguments['config_package_names']):
        filename = gen_out.cluster_packages[package_name]['filename']
        copy_makedirs(filename, output_dir + filename)

    # Write an index of the cluster packages
    write_json(output_dir + 'cluster-package-info.json', gen_out.cluster_packages)

    # Write the bootstrap id
    write_string(output_dir + 'bootstrap.latest', gen_out.arguments['bootstrap_id'])


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
