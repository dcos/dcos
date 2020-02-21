"""
Generating upgrade script for Windows agent (dcos_node_upgrade.ps1)
"""

import uuid

import gen.build_deploy.util as util
import gen.calc
import gen.template
from dcos_installer.constants import SERVE_DIR
from pkgpanda.util import make_directory, write_string


node_upgrade_template = r"""
<#
.SYNOPSIS
  Name: dcos_node_upgrade.ps1
  The purpose of this script is to Upgrade DC/OS packages on Windows agent and start Winpanda of DC/OS cluster.

.EXAMPLE
#  .\dcos_install.ps1 <bootstrap_url> <masters>
#  .\dcos_install.ps1 "http://int-bootstrap1-examplecluster.example.com:8080/<version>/genconf/serve" "master1,master2"

# requires -version 2
#>

# Metadata:
#   dcos image commit : {{ dcos_image_commit }}
#   generation date   : {{ generation_date }}

[CmdletBinding()]

# PARAMETERS
param (
    [Parameter(Mandatory=$false)] [string] $bootstrap_url = '{{ bootstrap_url }}',
    [Parameter(Mandatory=$false)] [string] $masters = '{{ master_list }}',
    [Parameter(Mandatory=$false)] [string] $install_dir = 'C:\d2iq\dcos',
    [Parameter(Mandatory=$false)] [string] $var_dir = 'C:\d2iq\dcos\var'
)

# GLOBAL
$global:basedir = "$($install_dir)"
$global:vardir  = "$($var_dir)"

$ErrorActionPreference = "Stop"

echo $bootstrap_url
echo $masters.replace('"', '').replace('[', '').replace(']', '').replace(' ', '')
"""


def generate_node_upgrade_win_script(gen_out, installed_cluster_version, serve_dir=SERVE_DIR):

    # installed_cluster_version: Current installed version on the cluster
    # installer_version: Version we are upgrading to

    bootstrap_url = gen_out.arguments['bootstrap_url']
    master_list = gen_out.arguments['master_list']
    installer_version = gen.calc.entry['must']['dcos_version']

    powershell_script = gen.template.parse_str(node_upgrade_template).render({
        'dcos_image_commit': util.dcos_image_commit,
        'generation_date': util.template_generation_date,
        'bootstrap_url': bootstrap_url,
        'master_list': master_list,
        'installed_cluster_version': installed_cluster_version,
        'installer_version': installer_version})

    upgrade_script_path = '/windows/upgrade/' + uuid.uuid4().hex
    make_directory(serve_dir + upgrade_script_path)
    write_string(serve_dir + upgrade_script_path + '/dcos_node_upgrade.ps1', powershell_script)
    print("Windows agent upgrade script URL: " + bootstrap_url + upgrade_script_path + '/dcos_node_upgrade.ps1')
    return 0
