"""
Generating upgrade script for Windows agent (dcos_node_upgrade.ps1)
"""

import os.path

import uuid

import gen.build_deploy.util as util
import gen.calc
import gen.template
from dcos_installer.constants import SERVE_DIR
from pkgpanda.util import make_directory, write_string


def generate_node_upgrade_win_script(gen_out, installed_cluster_version, serve_dir=SERVE_DIR):

    # installed_cluster_version: Current installed version on the cluster
    # installer_version: Version we are upgrading to

    bootstrap_url = gen_out.arguments['bootstrap_url']
    if gen_out.arguments['master_discovery'] == 'static':
        master_list = gen_out.arguments['master_list']
    elif gen_out.arguments['master_discovery'] == 'master_http_loadbalancer':
        master_list = gen_out.arguments['exhibitor_address'] + ':2181'
    else:
        master_list = 'zk-1.zk:2181,zk-2.zk:2181,zk-3.zk:2181,zk-4.zk:2181,zk-5.zk:2181'

    installer_version = gen.calc.entry['must']['dcos_version']

    node_upgrade_template_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                              'gen/build_deploy/powershell/dcos_node_upgrade.ps1.in')
    with open(node_upgrade_template_path, 'r') as f:
        node_upgrade_template = f.read()
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
