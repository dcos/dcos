import ssh.ssh_runner

REMOTE_TEMP_DIR = '/opt/dcos_install_tmp'
CLUSTER_PACKAGES_FILE = '/genconf/cluster_packages.json'


def get_async_runner(config, hosts, async_delegate=None):
    process_timeout = config.get('process_timeout', 120)
    extra_ssh_options = config.get('extra_ssh_options', '')
    ssh_key_path = config.get('ssh_key_path', '/genconf/ssh_key')

    # if ssh_parallelism is not set, use 20 concurrent ssh sessions by default.
    parallelism = config.get('ssh_parallelism', 20)

    return ssh.ssh_runner.MultiRunner(hosts, ssh_user=config['ssh_user'], ssh_key_path=ssh_key_path,
                                      process_timeout=process_timeout, extra_opts=extra_ssh_options,
                                      async_delegate=async_delegate, parallelism=parallelism)


def add_pre_action(chain, ssh_user):
    # Do setup steps for a chain
    chain.add_execute(['sudo', 'mkdir', '-p', REMOTE_TEMP_DIR], stage='Creating temp directory')
    chain.add_execute(['sudo', 'chown', ssh_user, REMOTE_TEMP_DIR],
                      stage='Ensuring {} owns temporary directory'.format(ssh_user))


def add_post_action(chain):
    # Do cleanup steps for a chain
    chain.add_execute(['sudo', 'rm', '-rf', REMOTE_TEMP_DIR],
                      stage='Cleaning up temporary directory')
