"""Launch a cluster of hosts

Usage:
    dcos-launch [--config=config.yaml]
    # gce <num_hosts> <path_to_dcos_generate_config>
    # dcos-launch aws
    #     vpc
    # dcos-launch ccm vpc
    # dcos-launch vpc {ccm,aws,gce,vagrant} {num_hosts}
    # dcos-launch cloudformation
    # dcos-launch
    # dcos-launch connect <config.yaml> # {ccm,aws,gce,vagrant}
    # dcos-launch <aws> <vpc>
    # dcos-launch <vpc> <aws>
    # Build up an index of "launchables"?
    # - Can then compose into things which take that API shape?
"""
import argparse
import sys

import yaml

from test_util.gce import GceVpc
from test_util.installer_runner import do_install


def main():
    parser = argparse.ArgumentParser(description='Launches a DC/OS cluster using the specified config')
    parser.add_argument('--config', default='config.yaml')

    arguments = parser.parse_args()

    with open(arguments.config, 'r') as config_file:
        config = yaml.load(config_file)

    vpc = GceVpc(
        deployment=config['deployment'],
        description=config.get('description', 'DC/OS Dev Testing'),
        project=config['project'],
        zone=config.get('zone', 'us-central1-b'),
        credentials_filename=config.get('credentials_filename', 'gce-credentials.json'))

    num_master = config.get('num_master', 1)
    num_agent = config.get('num_agent', 3)
    num_agent_public = config.get('num_agent_public', 1)

    # Test host + all other hosts
    host_count = 1 + num_master + num_agent + num_agent_public
    vpc.launch(host_count)
    vpc.wait_for_done()

    hosts = vpc.get_ips()
    test_host = hosts.pop()
    master_list = [hosts.pop() for i in range(num_master)]
    agent_list = [hosts.pop() for i in range(num_agent)]
    public_agent_list = [hosts.pop() for i in range(num_agent_public)]

    try:
        do_install(
            installer_url=config.get('installer_url', 'https://downloads.dcos.io/dcos/stable/dcos_generate_config.sh'),
            ssh_user='ops_shared',
            ssh_key_path='/Users/codymaloney/.ssh/mesosphere_shared',
            test_host=test_host,
            master_list=master_list,
            agent_list=agent_list,
            public_agent_list=public_agent_list,
            method='ssh',  # TODO(cmaloney): MAke configurable
            install_prereqs=True,
            do_setup=True,
            remote_dir='/home/centos',
            add_config_path=None,
            stop_after_prereqs=False,
            run_test=True,
            aws_region=None,
            dcos_variant='',
            provider='onprem',
            ci_flags=None,
            aws_access_key_id=None,
            aws_secret_access_key=None,
            add_env={})
    except Exception as ex:
        print("ERROR: {}".format(ex))
        try:
            while True:
                choice = input("Delete cluster [yes/No]:").lower()
                if 'yes'.startswith(choice):
                    vpc.delete()
                    break
                if 'no'.startswith(choice) or choice == '':
                    break
        except KeyboardInterrupt as ex:
            pass
        except Exception as ex:
            print("ERROR while getting input: {}".format(ex))
        sys.exit(1)

    sys.exit(0)

