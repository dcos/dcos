import os
import shutil
from datetime import datetime
from subprocess import check_output

import pkgpanda
from pkgpanda.util import load_json, write_json, write_string

dcos_image_commit = os.getenv('DCOS_IMAGE_COMMIT', None)

if dcos_image_commit is None:
    dcos_image_commit = check_output(['git', 'rev-parse', 'HEAD']).decode('utf-8').strip()

if dcos_image_commit is None:
    raise "Unable to set dcos_image_commit from teamcity or git."

template_generation_date = str(datetime.utcnow())


def cluster_to_extra_packages(cluster_packages):
    return [pkg['id'] for pkg in cluster_packages.values()]


def try_makedirs(path):
    try:
        os.makedirs(path)
    except FileExistsError:
        pass


def copy_makedirs(src, dest):
    try_makedirs(os.path.dirname(dest))
    shutil.copy(src, dest)

fetch_pkg_template = """
mkdir -p $(dirname {package_path})
curl -fLsSv --retry 20 -Y 100000 -y 60 -o {package_path} {bootstrap_url}/{package_path}
"""

fetch_all_pkgs = """#!/bin/bash
set -euo pipefail
set -x

{package_fetches}
"""


def do_bundle_onprem(extra_files, gen_out, output_dir):
    # We are only being called via dcos_generate_config.sh with an output_dir
    assert output_dir is not None
    assert output_dir
    assert output_dir[-1] != '/'
    output_dir = output_dir + '/'

    # Copy the extra_files
    for filename in extra_files:
        shutil.copy(filename, output_dir + filename)

    # Copy the cluster packages
    for name, info in gen_out.cluster_packages.items():
        copy_makedirs(info['filename'], output_dir + info['filename'])

    # Write an index of the cluster packages
    write_json(output_dir + 'cluster-package-info.json', gen_out.cluster_packages)

    # Write the bootstrap id
    write_string(output_dir + 'bootstrap.latest', gen_out.arguments['bootstrap_id'])

    # Make a package fetch script
    package_fetches = "\n".join(
        fetch_pkg_template.format(
            package_path='packages/{name}/{id}.tar.xz'.format(name=pkgpanda.PackageId(package).name, id=package),
            bootstrap_url='https://downloads.dcos.io/dcos/stable'
            ) for package in load_json("/artifacts/{}.active.json".format(gen_out.arguments['bootstrap_id'])))
    write_string(output_dir + 'fetch_packages.sh', fetch_all_pkgs.format(package_fetches=package_fetches))


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
