"""
Generating node upgrade script
"""

import uuid

import gen.build_deploy.util as util
import gen.calc
import gen.template
from dcos_installer.constants import SERVE_DIR
from pkgpanda.util import make_directory, write_string


node_upgrade_template = """#!/bin/bash
#
# BASH script to upgrade DC/OS on a node
#
# Metadata:
#   dcos image commit: {{ dcos_image_commit }}
#   generation date: {{ generation_date }}
#
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

set -o errexit -o pipefail -o nounset

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

SKIP_CHECKS=false
VERBOSE=false

if [[ $# -ne 0 ]]; then
    for var in "$@"; do
        if [[ "$var" = "--skip-checks" ]]; then
            echo "Skipping checks"
            SKIP_CHECKS=true
        fi
        if [[ "$var" = "--verbose" ]]; then
            echo "Verbose mode on"
            VERBOSE=true
        fi
    done
fi

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root" 1>&2
    exit 1
fi

# check for version of dc/os upgrading from
found_version=`grep "version" /opt/mesosphere/etc/dcos-version.json | cut -d '"' -f 4`
if [[ "$found_version" != "{{ installed_cluster_version }}" ]]; then
    echo "ERROR: Expecting to upgrade DC/OS from {{ installed_cluster_version }} to {{ installer_version }}." \
         "Version found on node: $found_version"
    exit 1
fi

if [[ "$SKIP_CHECKS" = "false" ]]; then
   # Check if the node has node/cluster checks and run them
   if [ -f /opt/mesosphere/etc/dcos-diagnostics-runner-config.json ]; then
      # command exists
      if ! output="$(dcos-diagnostics check node-poststart 2>&1)"; then
          echo "Cannot proceed with upgrade, node checks failed"
          echo >&2 "$output"
          exit 1
      fi

      if ! clusteroutput="$(dcos-diagnostics check cluster 2>&1)"; then
          echo "Cannot proceed with upgrade, cluster checks failed"
          echo >&2 "$clusteroutput"
          exit 1
      fi
   fi
fi

# Determine this node's role.
ROLE_DIR=/etc/mesosphere/roles

num_roles=$( (ls --format=single-column $ROLE_DIR/{master,slave,slave_public} || true) 2>/dev/null | wc -l)
if [ "$num_roles" -ne "1" ]; then
    echo "ERROR: Can't determine this node's role." \
         "One of master, slave, or slave_public must be present under $ROLE_DIR."
    exit 1
fi

if [ -f $ROLE_DIR/master ]; then
    role="master"
    role_name="master"
elif [ -f $ROLE_DIR/slave ]; then
    role="slave"
    role_name="agent"
elif [ -f $ROLE_DIR/slave_public ]; then
    role="slave_public"
    role_name="public agent"
fi


if [[ "$VERBOSE" = "true" ]]; then
    exec 3>&1
else
    exec 3>/dev/null
fi

echo "Upgrading DC/OS $role_name {{ installed_cluster_version }} -> {{ installer_version }}"
pkgpanda fetch --repository-url={{ bootstrap_url }} {{ cluster_packages }} >&3
pkgpanda activate --no-block {{ cluster_packages }} >&3

if [[ "$SKIP_CHECKS" = "false" ]]; then
    T=300
    until OUT="$(dcos-diagnostics check node-poststart && dcos-diagnostics check cluster 2>&1)" || [[ $T -eq 0 ]]; do
      sleep 1
      let T=T-1
    done
    RETCODE=$?
    if [[ $RETCODE -ne 0 ]]; then
       echo "Node upgrade not successful, checks failed"
       echo >&2 "$OUT"
    fi
    exit $RETCODE
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

    make_directory(serve_dir + upgrade_script_path)

    write_string(serve_dir + upgrade_script_path + '/dcos_node_upgrade.sh', bash_script)

    print("Node upgrade script URL: " + bootstrap_url + upgrade_script_path + '/dcos_node_upgrade.sh')

    return 0
