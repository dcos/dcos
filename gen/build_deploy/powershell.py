"""
Generates a powershell script to install Windows agent - dcos_install.ps1
"""

import os
import os.path

import gen.build_deploy.util as util
import gen.template
import gen.util

import pkgpanda
import pkgpanda.util


def generate(gen_out, output_dir):
    print("Generating Powershell configuration files for DC/OS")
    make_powershell(gen_out, output_dir)


def make_powershell(gen_out, output_dir):
    """Build powershell deployment script and store this at Bootstrap serve"""

    output_dir = output_dir + '/windows/'
    pkgpanda.util.make_directory(output_dir)

    bootstrap_url = gen_out.arguments['bootstrap_url']
    if gen_out.arguments['master_discovery'] == 'static':
        master_list = gen_out.arguments['master_list']
    elif gen_out.arguments['master_discovery'] == 'master_http_loadbalancer':
        master_list = gen_out.arguments['exhibitor_address'] + ':2181'
    else:
        master_list = 'zk-1.zk:2181,zk-2.zk:2181,zk-3.zk:2181,zk-4.zk:2181,zk-5.zk:2181'

    powershell_template_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                            'powershell/dcos_install.ps1.in')
    with open(powershell_template_path, 'r') as f:
        powershell_template = f.read()
        powershell_script = gen.template.parse_str(powershell_template).render({
            'dcos_image_commit': util.dcos_image_commit,
            'generation_date': util.template_generation_date,
            'bootstrap_url': bootstrap_url,
            'master_list': master_list,
            })
    # Output the dcos install ps1 script
    install_script_filename = 'dcos_install.ps1'
    pkgpanda.util.write_string(install_script_filename, powershell_script)
    pkgpanda.util.write_string(output_dir + install_script_filename, powershell_script)
    f.close()
