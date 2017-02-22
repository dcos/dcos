'''
Generating node upgrade script
'''

import subprocess
import uuid

import gen.build_deploy.util as util
import gen.calc
import gen.template
from dcos_installer.constants import SERVE_DIR
from pkgpanda.util import write_string


node_upgrade_template = """
#!/bin/bash
#
# BASH script to upgrade DC/OS on a node
#
# Metadata:
#   dcos image commit: {{ dcos_image_commit }}
#   generation date: {{ generation_date }}
# Copyright 2017 Mesosphere, Inc.
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

# check for version of dc/os upgrading from
version=`grep "version" /opt/mesosphere/etc/dcos-version.json | cut -d '"' -f 4`
if [ "$version" != "{{ installed_cluster_version }}" ]; then
    echo "ERROR: Expecting to upgrade DC/OS from {{ installed_cluster_version }} to {{ installer_version }}.\
                 Version found on node: $version"
    exit 1
fi

# Determine this node's role.
ROLE_DIR=/etc/mesosphere/roles
if [ -f $ROLE_DIR/master ]; then
    role="master"
    role_name="master"
elif [ -f $ROLE_DIR/slave ]; then
    role="slave"
    role_name="agent"
elif [ -f $ROLE_DIR/slave_public ]; then
    role="slave_public"
    role_name="public agent"
else
    echo "ERROR: Can't determine this node's role." \
         "One of master, slave, or slave_public must be present under $ROLE_DIR."
    exit 1
fi

echo "Upgrading DC/OS $role_name {{ installed_cluster_version }} -> {{ installer_version }}"
pkgpanda fetch --repository-url={{ bootstrap_url }} {{ cluster_packages }}
pkgpanda activate --no-block {{ cluster_packages }}

# If this is a master node, migrate Exhibitor data to the correct directory.
if [ "$role" == "master" ]; then
    # run exhibitor migration script here
    until dcos-shell dcos-exhibitor-migrate-perform
    do
        status=$?
        case $status in
            1) echo "Waiting for exhibitor endpoint"
               sleep 10
               ;;
            2) echo "Could not read from exhibitor"
               echo "Contact Support"
               exit
               ;;
            4) echo "Rolling update in progress"
               exit
               ;;
            8) echo "At least one config value does not have the expected pre migration value,
                     \ and automatic migration can not take place"
               echo "Contact Support"
               exit
               ;;
            16) echo "Attempting to start the rolling update failed due to a non 200 response from exhibitor"
                echo "Contact Support"
                exit
                ;;
        esac
    done
fi

"""


def generate_node_upgrade_script(gen_out, installed_cluster_version, serve_dir=SERVE_DIR):

    # installed_cluster_version: Current installed version on the cluster
    # installer_version: Version we are upgrading to

    bootstrap_url = gen_out.arguments['bootstrap_url']

    installer_version = gen.calc.entry['must']['dcos_version']

    package_list = ' '.join(package['id'] for package in gen_out.cluster_packages.values())

    bash_script = gen.template.parse_str(node_upgrade_template).render({
        'dcos_image_commit': util.dcos_image_commit,
        'generation_date': util.template_generation_date,
        'bootstrap_url': bootstrap_url,
        'cluster_packages': package_list,
        'installed_cluster_version': installed_cluster_version,
        'installer_version': installer_version})

    upgrade_script_path = '/upgrade/' + uuid.uuid4().hex

    subprocess.check_call(['mkdir', '-p', serve_dir + upgrade_script_path])

    write_string(serve_dir + upgrade_script_path + '/dcos_node_upgrade.sh', bash_script)

    print("Node upgrade script URL: " + bootstrap_url + upgrade_script_path + '/dcos_node_upgrade.sh')

    return 0
