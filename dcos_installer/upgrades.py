'''
Generating node upgrade script
'''
import subprocess

import gen.build_deploy.util as util
import gen.template
from dcos_installer.constants import SERVE_DIR
from pkgpanda.build import hash_str
from pkgpanda.util import (if_exists, load_json, write_string)


node_upgrade_template = """
#!/bin/bash
#
# BASH script to upgrade DC/OS on a node
#
# Metadata:
#   dcos image commit: {{ dcos_image_commit }}
#   generation date: {{ generation_date }}
# Copyright 2016 Mesosphere, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -o errexit -o nounset -o pipefail

source /opt/mesosphere/environment.export

# Check if this is a terminal, and if colors are supported, set some basic
# colors for outputs
if [ -t 1 ]; then
    colors_supported=$(tput colors)
    if [[ $colors_supported -ge 8 ]]; then
    RED='\e[1;31m'
    BOLD='\e[1m'
    NORMAL='\e[0m'
    fi
fi

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root" 1>&2
    exit 1
fi


function main() {

    # check for version of dc/os upgrading from
    version=`grep "version" /opt/mesosphere/etc/dcos-version.json | cut -d '"' -f 4`
    if [ $version != {{ dcos_version }} ]; then
       echo "Not the correct version"
       exit 0
    fi

    pkgpanda fetch --repository-url={{ bootstrap_url }} {{ cluster_packages }}

    pkgpanda fetch --repository-url=https://downloads.dcos.io/dcos/testing {{ package_list }}

    pkgpanda activate {{ cluster_packages }} {{ package_list }}

    # check if we are on a master node
    if [ -f /etc/mesosphere/roles/master ]; then
       # run exhibitor migration script here
       dcos-shell dcos-exhibitor-migrate-perform
    fi

}

main
"""


def get_package_list(cluster_packages):
    setup_packages_to_activate = []

    for package in cluster_packages:
        setup_packages_to_activate.append(cluster_packages[package]['id'])

    return ' '.join(setup_packages_to_activate)


def generate_node_upgrade_script(gen_out, current_version, serve_dir=SERVE_DIR):

    bootstrap_url = gen_out.arguments['bootstrap_url']

    # remove once i have late binding stuff
    active_packages = serve_dir + '/bootstrap/' + gen_out.arguments['bootstrap_id'] + '.active.json'

    package_list = get_package_list(gen_out.cluster_packages)

    packages_to_activate = []

    active = if_exists(load_json, active_packages)
    for package in active:
        packages_to_activate.append(package)

    bash_script = gen.template.parse_str(node_upgrade_template).render({
        'dcos_image_commit': util.dcos_image_commit,
        'generation_date': util.template_generation_date,
        'bootstrap_url': bootstrap_url,
        'package_list': (' '.join(packages_to_activate)),
        'cluster_packages': package_list,
        'dcos_version': current_version})

    hash_string = hash_str(bash_script)
    upgrade_script_path = '/upgrade/' + hash_string

    subprocess.check_call(['mkdir', '-p', serve_dir + upgrade_script_path])

    write_string(serve_dir + upgrade_script_path + '/dcos_node_upgrade.sh', bash_script)
    write_string(serve_dir + '/upgrade.latest', hash_string)

    print("Node upgrade script URL: " + bootstrap_url + upgrade_script_path + '/dcos_node_upgrade.sh')

    return 0
