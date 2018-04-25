"""Generates a bash script for installing by hand or light config management integration"""

import json
import os
import os.path
import shutil
import subprocess
import tempfile

import checksumdir
import pkg_resources

import dcos_installer.config_util
import gen.build_deploy.util as util
import gen.template
import gen.util
import pkgpanda
import pkgpanda.util
from gen.calc import (
    calculate_environment_variable,
    CHECK_SEARCH_PATH as DEFAULT_CHECK_SEARCH_PATH,
    validate_true_false,
)
from gen.internals import Source
from pkgpanda.constants import (
    cloud_config_yaml, dcos_services_yaml, install_root
)
from pkgpanda.util import copy_directory, copy_file, is_windows, logger, make_directory


def calculate_custom_check_bins_provided(custom_check_bins_dir):
    if os.path.isdir(custom_check_bins_dir):
        return 'true'
    return 'false'


def calculate_custom_check_bins_hash(custom_check_bins_provided, custom_check_bins_dir):
    if custom_check_bins_provided == 'true':
        return checksumdir.dirhash(custom_check_bins_dir, 'sha1')
    return ''


def calculate_custom_check_bins_package_id(
        custom_check_bins_provided,
        custom_check_bins_package_name,
        custom_check_bins_hash):
    if custom_check_bins_provided == 'true':
        assert custom_check_bins_hash
        return '{}--{}'.format(custom_check_bins_package_name, custom_check_bins_hash)
    return ''


def calculate_check_search_path(custom_check_bins_provided, custom_check_bins_package_id):
    if custom_check_bins_provided == 'true':
        assert custom_check_bins_package_id != ''
        return (DEFAULT_CHECK_SEARCH_PATH + ':' + install_root + '/' +
                'packages/{}'.format(custom_check_bins_package_id))
    return DEFAULT_CHECK_SEARCH_PATH


def calculate_package_ids(bootstrap_variant, custom_check_bins_provided, custom_check_bins_package_id):
    package_ids = dcos_installer.config_util.installer_latest_complete_artifact(bootstrap_variant)['packages']
    if custom_check_bins_provided == 'true':
        assert custom_check_bins_package_id != ''
        package_ids.append(custom_check_bins_package_id)
    return json.dumps(package_ids)


def validate_custom_check_bins_dir(custom_check_bins_dir):
    assert len(custom_check_bins_dir) > 0, 'custom_check_bins_dir must be a valid directory name'
    if os.path.exists(custom_check_bins_dir):
        assert os.path.isdir(custom_check_bins_dir), '{} must be a directory'.format(custom_check_bins_dir)
        for entry in os.scandir(custom_check_bins_dir):
            assert entry.is_file(), '{} must not contain any subdirectories'.format(custom_check_bins_dir)


onprem_source = Source(entry={
    'validate': [
        validate_custom_check_bins_dir,
        lambda custom_check_bins_provided: validate_true_false(custom_check_bins_provided),
    ],
    'default': {
        'platform': 'onprem',
        'resolvers': '["8.8.8.8", "8.8.4.4"]',
        'ip_detect_filename': 'genconf/ip-detect',
        'ip6_detect_filename': '',
        'bootstrap_id': lambda: calculate_environment_variable('BOOTSTRAP_ID'),
        'enable_docker_gc': 'false'
    },
    'must': {
        'provider': 'onprem',
        'package_ids': calculate_package_ids,
        'custom_check_bins_dir': 'genconf/check_bins/',
        'custom_check_bins_package_name': 'custom-check-bins',
        'custom_check_bins_provided': calculate_custom_check_bins_provided,
        'custom_check_bins_hash': calculate_custom_check_bins_hash,
        'custom_check_bins_package_id': calculate_custom_check_bins_package_id,
        'check_search_path': calculate_check_search_path,
    },
})


file_template = """mkdir -p `dirname {filename}`
cat <<'EOF' > "{filename}"
{content}
EOF
chmod {mode} {filename}

"""

bash_template = """#!/bin/bash
#
# BASH script to install DC/OS on a node
#
# Usage:
#
#   dcos_install.sh <role>...
#
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

set -o errexit -o nounset -o pipefail

declare -i OVERALL_RC=0
declare -i PREFLIGHT_ONLY=0
declare -i DISABLE_PREFLIGHT=0
declare -i SYSTEMCTL_NO_BLOCK=0

declare ROLES=""
declare RED=""
declare BOLD=""
declare NORMAL=""

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

# Setup getopt argument parser
ARGS=$(getopt -o dph --long "disable-preflight,preflight-only,help,no-block-dcos-setup" -n "$(basename "$0")" -- "$@")

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root" 1>&2
    exit 1
fi

function setup_directories() {
    echo -e "Creating directories under /etc/mesosphere"
    mkdir -p /etc/mesosphere/roles
    mkdir -p /etc/mesosphere/setup-flags
}

function setup_dcos_roles() {
    # Set DC/OS roles
    for role in $ROLES
    do
        echo "Creating role file for ${role}"
        touch "/etc/mesosphere/roles/$role"
    done
}

# Set DC/OS machine configuration
function configure_dcos() {
echo -e 'Configuring DC/OS'
{{ setup_flags }}
}

# Install the DC/OS services, start DC/OS
function setup_and_start_services() {

echo -e 'Setting and starting DC/OS'
{{ setup_services }}
}

set +e

declare -i DISABLE_VERSION_CHECK=0

# check if sort -V works
function check_sort_capability() {
    $( command -v sort >/dev/null 2>&1 || exit 1 )
    RC1=$?
    $( echo '1' | sort -V >/dev/null 2>&1 )
    RC2=$?
    if [[ "$RC1" -eq "1" || "$RC2" -eq "2" ]]; then
        echo -e "${RED}Disabling version checking as sort -V is not available${NORMAL}"
        DISABLE_VERSION_CHECK=1
    fi
}

function version_gt() {
    # sort -V does version-aware sort
    HIGHEST_VERSION="$(echo "$@" | tr " " "\n" | sort -V | tail -n 1)"
    test $HIGHEST_VERSION == "$1"
}

function print_status() {
    CODE_TO_TEST=$1
    EXTRA_TEXT=${2:-}
    if [[ $CODE_TO_TEST == 0 ]]; then
        echo -e "${BOLD}PASS $EXTRA_TEXT${NORMAL}"
    else
        echo -e "${RED}FAIL $EXTRA_TEXT${NORMAL}"
    fi
}

function check_command_exists() {
    COMMAND=$1
    DISPLAY_NAME=${2:-$COMMAND}

    echo -e -n "Checking if $DISPLAY_NAME is installed and in PATH: "
    $( command -v $COMMAND >/dev/null 2>&1 || exit 1 )
    RC=$?
    print_status $RC
    (( OVERALL_RC += $RC ))
    return $RC
}

function check_version() {
    COMMAND_NAME=$1
    VERSION_ATLEAST=$2
    COMMAND_VERSION=$3
    DISPLAY_NAME=${4:-$COMMAND}

    echo -e -n "Checking $DISPLAY_NAME version requirement (>= $VERSION_ATLEAST): "
    version_gt $COMMAND_VERSION $VERSION_ATLEAST
    RC=$?
    print_status $RC "${NORMAL}($COMMAND_VERSION)"
    (( OVERALL_RC += $RC ))
    return $RC
}

function check_selinux() {
  ENABLED=$(getenforce)

  if [[ $ENABLED != 'Enforcing' ]]; then
    RC=0
  else
    RC=1
  fi

  print_status $RC "Is SELinux disabled?"
  (( OVERALL_RC += $RC ))
  return $RC
}

function check() {
    # Wrapper to invoke both check_commmand and version check in one go
    if [[ $# -eq 4 ]]; then
       DISPLAY_NAME=$4
    elif [[ $# -eq 2 ]]; then
       DISPLAY_NAME=$2
    else
       DISPLAY_NAME=$1
    fi
    check_command_exists $1 $DISPLAY_NAME
    # check_version takes {3,4} arguments
    if [[ "$?" -eq 0 && "$#" -ge 3 && $DISABLE_VERSION_CHECK -eq 0 ]]; then
        check_version $*
    fi
}

function check_service() {
  PORT=$1
  NAME=$2
  echo -e -n "Checking if port $PORT (required by $NAME) is in use: "
  RC=0
  cat /proc/net/{udp*,tcp*} | cut -d: -f3 | cut -d' ' -f1 | grep -q $(printf "%04x" $PORT) && RC=1
  print_status $RC
  (( OVERALL_RC += $RC ))
}

function empty_dir() {
    # Return 0 if $1 is a directory containing no files.
    DIRNAME=$1

    RC=0
    if [[ ( ! -d "$DIRNAME" ) || $(ls -A "$DIRNAME") ]]; then
        RC=1
    fi
    return $RC
}

function check_preexisting_dcos() {
    echo -e -n 'Checking if DC/OS is already installed: '
    if (
        # dcos.target exists and is a directory, OR
        [[ -d /etc/systemd/system/dcos.target ]] ||
        # dcos.target.wants exists and is a directory, OR
        [[ -d /etc/systemd/system/dcos.target.wants ]] ||
        # /opt/mesosphere exists and is not an empty directory
        ( [[ -a /opt/mesosphere ]] && ( ! empty_dir /opt/mesosphere ) )
    ); then
        # this will print: Checking if DC/OS is already installed: FAIL (Currently installed)
        print_status 1 "${NORMAL}(Currently installed)"
        echo
        cat <<EOM
Found an existing DC/OS installation. To reinstall DC/OS on this this machine you must
first uninstall DC/OS then run dcos_install.sh. To uninstall DC/OS, follow the product
documentation provided with DC/OS.
EOM
        echo
        exit 1
    else
        print_status 0 "${NORMAL}(Not installed)"
    fi
}


function check_docker_device_mapper_loopback() {
    echo -e -n 'Checking Docker is configured with a production storage driver: '

  storage_driver="$(docker info | grep 'Storage Driver' | cut -d ':' -f 2  | tr -d '[[:space:]]')"

  if [ "$storage_driver" != "devicemapper" ]; then
      print_status 0 "${NORMAL}(${storage_driver})"
      return
  fi

  data_file="$(docker info | grep 'Data file' | cut -d ':' -f 2  | tr -d '[[:space:]]')"

  if [[ "${data_file}" == /dev/loop* ]]; then
    print_status 1 "${NORMAL}(${storage_driver}, ${data_file})"
    echo
    cat <<EOM
Docker is configured to use the devicemapper storage driver with a loopback
device behind it. This is highly recommended against by Docker and the
community at large for production use[0][1]. See the docker documentation on
selecting an alternate storage driver, or use alternate storage than loopback
for the devicemapper driver.

[0] https://docs.docker.com/engine/userguide/storagedriver/device-mapper-driver/
[1] http://www.projectatomic.io/blog/2015/06/notes-on-fedora-centos-and-docker-storage-drivers/
EOM
        echo
        exit 1
    else
        print_status 0 "${NORMAL}(${storage_driver} ${data_file})"
    fi
}

function check_all() {
    # Disable errexit because we want the preflight checks to run all the way
    # through and not bail in the middle, which will happen as it relies on
    # error exit codes
    set +e
    echo -e "${BOLD}Running preflight checks${NORMAL}"
    AGENT_ONLY=0
    for ROLE in $ROLES; do
        if [[ $ROLE = "slave" || $ROLE = "slave_public" ]]; then
            AGENT_ONLY=1
            break
        fi
    done

    check_preexisting_dcos
    check_selinux
    check_sort_capability

    local docker_version=$(command -v docker >/dev/null 2>&1 && docker version 2>/dev/null | awk '
        BEGIN {
            version = 0
            client_version = 0
            server_version = 0
        }
        {
            if($1 == "Server:") {
                server = 1
                client = 0
            } else if($1 == "Client:") {
                server = 0
                client = 1
            } else if ($1 == "Server" && $2 == "version:") {
                server_version = $3
            } else if ($1 == "Client" && $2 == "version:") {
                client_version = $3
            }
            if(server && $1 == "Version:") {
                server_version = $2
            } else if(client && $1 == "Version:") {
                client_version = $2
            }
        }
        END {
            if(client_version == server_version) {
                version = client_version
            } else {
                cv_length = split(client_version, cv, ".")
                sv_length = split(server_version, sv, ".")

                y = cv_length > sv_length ? cv_length : sv_length

                for(i = 1; i <= y; i++) {
                    if(cv[i] < sv[i]) {
                        version = client_version
                        break
                    } else if(sv[i] < cv[i]) {
                        version = server_version
                        break
                    }
                }
            }
            print version
        }
    ')
    # CoreOS stable as of Aug 2015 has 1.6.2
    check docker 1.6 "$docker_version"

    check curl
    check bash
    check ping
    check tar
    check xz
    check unzip
    check ipset
    check systemd-notify

    # $ systemctl --version ->
    # systemd nnn
    # compiler option string
    # Pick up just the first line of output and get the version from it
    check systemctl 200 $(systemctl --version | head -1 | cut -f2 -d' ') systemd

    echo -e -n "Checking if group 'nogroup' exists: "
    getent group nogroup > /dev/null
    RC=$?
    print_status $RC
    (( OVERALL_RC += $RC ))

    # Run service check on master node only
    if [[ $AGENT_ONLY -eq 0 ]]; then
        # master node service checks
        for service in \
            "53 dcos-net" \
            "80 adminrouter" \
            "443 adminrouter" \
            "1050 dcos-diagnostics" \
            "2181 zookeeper" \
            "5050 mesos-master" \
            "7070 cosmos" \
            "8080 marathon" \
            "8101 dcos-oauth" \
            "8123 mesos-dns" \
            "8181 exhibitor" \
            "9000 metronome" \
            "9942 metronome" \
            "9990 cosmos" \
            "15055 dcos-history" \
            "36771 marathon" \
            "41281 zookeeper" \
            "46839 metronome" \
            "61053 mesos-dns" \
            "61091 dcos-metrics" \
            "61420 dcos-net" \
            "62080 dcos-net" \
            "62501 dcos-net"
        do
            check_service $service
        done
    else
        # agent / public agent node service checks
        for service in \
            "53 dcos-net" \
            "5051 mesos-agent" \
            "61001 agent-adminrouter" \
            "61091 dcos-metrics" \
            "61420 dcos-net" \
            "62080 dcos-net" \
            "62501 dcos-net"
        do
            check_service $service
        done
    fi

    # Check we're not in docker on devicemapper loopback as storage driver.
    check_docker_device_mapper_loopback

    for role in "$ROLES"
    do
        if [ "$role" != "master" -a "$role" != "slave" -a "$role" != "slave_public" -a "$role" != "minuteman" ]; then
            echo -e "${RED}FAIL Invalid role $role. Role must be one of {master,slave,slave_public}${NORMAL}"
            (( OVERALL_RC += 1 ))
        fi
    done


    return $OVERALL_RC
}

function dcos_install()
{
    # Enable errexit
    set -e

    setup_directories
    setup_dcos_roles
    configure_dcos
    setup_and_start_services

}

function usage()
{
    echo -e "${BOLD}Usage: $0 [--disable-preflight|--preflight-only] <roles>${NORMAL}"
}

function main()
{
    eval set -- "$ARGS"

    while true ; do
        case "$1" in
            -d|--disable-preflight) DISABLE_PREFLIGHT=1;  shift  ;;
            -p|--preflight-only) PREFLIGHT_ONLY=1 ; shift  ;;
            --no-block-dcos-setup) SYSTEMCTL_NO_BLOCK=1;  shift ;;
            -h|--help) usage; exit 1 ;;
            --) shift ; break ;;
            *) usage ; exit 1 ;;
        esac
    done

    if [[ $DISABLE_PREFLIGHT -eq 1 && $PREFLIGHT_ONLY -eq 1 ]]; then
        echo -e 'Both --disable-preflight and --preflight-only can not be specified'
        usage
        exit 1
    fi

    shift $(($OPTIND - 1))
    ROLES=$@

    if [[ $PREFLIGHT_ONLY -eq 1 ]] ; then
        check_all
    else
        if [[ -z $ROLES ]] ; then
            echo -e 'Atleast one role name must be specified'
            usage
            exit 1
        fi
        echo -e "${BOLD}Starting DC/OS Install Process${NORMAL}"
        if [[ $DISABLE_PREFLIGHT -eq 0 ]] ; then
            check_all
            RC=$?
            if [[ $RC -ne 0 ]]; then
                echo 'Preflight checks failed. Exiting installation. Please consult product documentation'
                exit $RC
            fi
        fi
        # Run actual install
        dcos_install
    fi

}

# Run it all
main

"""

systemctl_no_block_service = """
if (( $SYSTEMCTL_NO_BLOCK == 1 )); then
    systemctl {command} {name} --no-block
else
    systemctl {command} {name}
fi
"""


def generate(gen_out, output_dir):
    print("Generating Bash configuration files for DC/OS")
    make_bash(gen_out)
    util.do_bundle_onprem(gen_out, output_dir)


def make_bash(gen_out) -> None:
    """Build bash deployment artifacts and return a list of their filenames."""
    # Build custom check bins package
    if gen_out.arguments['custom_check_bins_provided'] == 'true':
        package_filename = 'packages/{}/{}.tar.xz'.format(
            gen_out.arguments['custom_check_bins_package_name'],
            gen_out.arguments['custom_check_bins_package_id'],
        )
        make_custom_check_bins_package(gen_out.arguments['custom_check_bins_dir'], package_filename)
        gen_out.utils.add_stable_artifact(package_filename)

    setup_flags = ""
    cloud_config = gen_out.templates[cloud_config_yaml]
    # Assert the cloud-config is only write_files.
    assert len(cloud_config) == 1
    for file_dict in cloud_config['write_files']:
        # NOTE: setup-packages is explicitly disallowed. Should all be in extra
        # cluster packages.
        assert 'setup-packages' not in file_dict['path']
        setup_flags += file_template.format(
            filename=file_dict['path'],
            content=file_dict['content'],
            mode=file_dict.get('permissions', "0644"),
            owner=file_dict.get('owner', 'root'),
            group=file_dict.get('group', 'root'))

    # Reformat the DC/OS systemd units to be bash written and started.
    # Write out the units as files
    setup_services = ""
    for service in gen_out.templates[dcos_services_yaml]:
        # If no content, service is assumed to already exist
        if 'content' not in service:
            continue
        setup_services += file_template.format(
            filename='/etc/systemd/system/{}'.format(service['name']),
            content=service['content'],
            mode='0644',
            owner='root',
            group='root')

    setup_services += "\n"

    # Start, enable services which request it.
    for service in gen_out.templates[dcos_services_yaml]:
        assert service['name'].endswith('.service')
        name = service['name'][:-8]
        if service.get('enable'):
            setup_services += "systemctl enable {}\n".format(name)
        if 'command' in service:
            if service.get('no_block'):
                setup_services += systemctl_no_block_service.format(
                    command=service['command'],
                    name=name)
            else:
                setup_services += "systemctl {} {}\n".format(service['command'], name)

    # Populate in the bash script template
    bash_script = gen.template.parse_str(bash_template).render({
        'dcos_image_commit': util.dcos_image_commit,
        'generation_date': util.template_generation_date,
        'setup_flags': setup_flags,
        'setup_services': setup_services})

    # Output the dcos install script
    install_script_filename = 'dcos_install.sh'
    pkgpanda.util.write_string(install_script_filename, bash_script)
    gen_out.utils.add_channel_artifact(install_script_filename)


def make_custom_check_bins_package(source_dir, package_filename):
    with gen.util.pkgpanda_package_tmpdir() as tmpdir:
        tmp_source_dir = os.path.join(tmpdir, 'check_bins')
        shutil.copytree(source_dir, tmp_source_dir)

        # Apply permissions
        for entry in os.scandir(tmp_source_dir):
            # source_dir should have no subdirs.
            assert entry.is_file()
            os.chmod(entry.path, 0o755)

        # Add an empty pkginfo.json.
        pkginfo_filename = os.path.join(tmp_source_dir, 'pkginfo.json')
        assert not os.path.isfile(pkginfo_filename)
        with open(pkginfo_filename, 'w') as f:
            f.write('{}')
        os.chmod(pkginfo_filename, 0o644)

        gen.util.make_pkgpanda_package(tmp_source_dir, package_filename)


def make_installer_docker(variant, variant_info, installer_info):
    bootstrap_id = variant_info['bootstrap']
    assert len(bootstrap_id) > 0

    image_version = util.dcos_image_commit[:18] + '-' + bootstrap_id[:18]
    genconf_tar = "dcos-genconf." + image_version + ".tar"
    installer_filename = "packages/cache/dcos_generate_config." + pkgpanda.util.variant_prefix(variant) + "sh"
    bootstrap_filename = bootstrap_id + ".bootstrap.tar.xz"
    bootstrap_active_filename = bootstrap_id + ".active.json"
    installer_bootstrap_filename = installer_info['bootstrap'] + '.bootstrap.tar.xz'
    bootstrap_latest_filename = pkgpanda.util.variant_prefix(variant) + 'bootstrap.latest'
    latest_complete_filename = pkgpanda.util.variant_prefix(variant) + 'complete.latest.json'
    packages_dir = 'packages'
    docker_image_name = 'mesosphere/dcos-genconf:' + image_version

    # TODO(cmaloney): All of this should use package_resources
    with tempfile.TemporaryDirectory() as build_dir:
        assert build_dir[-1] != '/'

        print("Setting up build environment")

        def dest_path(filename):
            return build_dir + '/' + filename

        def copy_to_build(src_prefix, filename):
            dest_filename = dest_path(filename)
            os.makedirs(os.path.dirname(dest_filename), exist_ok=True)
            copy_file(os.getcwd() + '/' + src_prefix + '/' + filename, dest_filename)

        def fill_template(base_name, format_args):
            pkgpanda.util.write_string(
                dest_path(base_name),
                pkg_resources.resource_string(__name__, 'bash/' + base_name + '.in').decode().format(**format_args))

        fill_template('Dockerfile', {
            'installer_bootstrap_filename': installer_bootstrap_filename,
            'bootstrap_filename': bootstrap_filename,
            'bootstrap_active_filename': bootstrap_active_filename,
            'bootstrap_latest_filename': bootstrap_latest_filename,
            'latest_complete_filename': latest_complete_filename,
            'packages_dir': packages_dir})

        fill_template('installer_internal_wrapper', {
            'variant': pkgpanda.util.variant_str(variant),
            'bootstrap_id': bootstrap_id,
            'dcos_image_commit': util.dcos_image_commit})

        if not is_windows:
            subprocess.check_call(['chmod', '+x', dest_path('installer_internal_wrapper')])

        # TODO(cmaloney) make this use make_bootstrap_artifacts / that set
        # rather than manually keeping everything in sync
        copy_to_build('packages/cache/bootstrap', bootstrap_filename)
        copy_to_build('packages/cache/bootstrap', installer_bootstrap_filename)
        copy_to_build('packages/cache/bootstrap', bootstrap_active_filename)
        copy_to_build('packages/cache/bootstrap', bootstrap_latest_filename)
        copy_to_build('packages/cache/complete', latest_complete_filename)
        for package_id in variant_info['packages']:
            package_name = pkgpanda.PackageId(package_id).name
            copy_to_build('packages/cache/', packages_dir + '/' + package_name + '/' + package_id + '.tar.xz')

        # Copy across gen_extra if it exists
        if os.path.exists('gen_extra'):
            copy_directory('gen_extra', dest_path('gen_extra'))
        else:
            make_directory(dest_path('gen_extra'))

        print("Building docker container in " + build_dir)
        subprocess.check_call(['docker', 'build', '-t', docker_image_name, build_dir])

        print("Building", installer_filename)
        pkgpanda.util.write_string(
            installer_filename,
            pkg_resources.resource_string(__name__, 'bash/dcos_generate_config.sh.in').decode().format(
                genconf_tar=genconf_tar,
                docker_image_name=docker_image_name,
                variant=variant) + '\n#EOF#\n')
        subprocess.check_call(
            ['docker', 'save', docker_image_name],
            stdout=open(genconf_tar, 'w'))
        subprocess.check_call(['tar', 'cvf', '-', genconf_tar], stdout=open(installer_filename, 'a'))
        subprocess.check_call(['chmod', '+x', installer_filename])

        # Cleanup
        subprocess.check_call(['rm', genconf_tar])

    return installer_filename


def do_create(tag, build_name, reproducible_artifact_path, commit, variant_arguments, all_completes):
    """Create a installer script for each variant in bootstrap_dict.

    Writes a dcos_generate_config.<variant>.sh for each variant in
    bootstrap_dict to the working directory, except for the default variant's
    script, which is written to dcos_generate_config.sh. Returns a dict mapping
    variants to (genconf_version, genconf_filename) tuples.

    Outputs the generated dcos_generate_config.sh as it's artifacts.
    """
    # TODO(cmaloney): Build installers in parallel.
    # Variants are sorted for stable ordering.
    for variant in sorted(variant_arguments.keys(), key=lambda k: pkgpanda.util.variant_str(k)):
        variant_name = pkgpanda.util.variant_name(variant)
        bootstrap_installer_name = '{}installer'.format(pkgpanda.util.variant_prefix(variant))
        if bootstrap_installer_name not in all_completes:
            print('WARNING: No installer tree for variant: {}'.format(variant_name))
        else:
            with logger.scope("Building installer for variant: {}".format(variant_name)):

                yield {
                    'channel_path': 'dcos_generate_config.{}sh'.format(pkgpanda.util.variant_prefix(variant)),
                    'local_path': make_installer_docker(variant, all_completes[variant],
                                                        all_completes[bootstrap_installer_name])
                }
