import os
import socket
import stat


def validate_ssh_user(ssh_user):
    assert ssh_user, 'ssh_user must be set'
    assert isinstance(ssh_user, str), 'ssh_user must be a string'


def validate_ssh_key_path(ssh_key_path):
    assert isinstance(ssh_key_path, str), 'ssh_key_path must be a string'
    assert ssh_key_path, 'ssh_key_path must be set'
    assert os.path.isfile(ssh_key_path), 'could not find ssh private key: {}'.format(ssh_key_path)
    assert stat.S_IMODE(
        os.stat(ssh_key_path).st_mode) & (stat.S_IRWXG + stat.S_IRWXO) == 0, (
            'ssh_key_path must be only read / write / executable by the owner. It may not be read / write / executable '
            'by group, or other.')
    with open(ssh_key_path) as fh:
        assert 'ENCRYPTED' not in fh.read(), ('Encrypted SSH keys (which contain passphrases) '
                                              'are not allowed. Use a key without a passphrase.')


def validate_ssh_port(ssh_port):
    # Validate ssh port between 1 - 32000
    assert isinstance(ssh_port, int), 'ssh port should be integer'
    assert 1 <= ssh_port <= 32000, 'ssh port should be int between 1 - 32000'


def validate_hosts_list(nodes_list, name):
    assert nodes_list, name + ' must be set'
    assert isinstance(nodes_list, list), name + ' must be a list'
    check_duplicates(nodes_list)
    check_ipv4_addrs(nodes_list)


def validate_master_agent_lists(master_list, agent_list, public_agent_list):
    validate_hosts_list(master_list, 'master_list')

    # Require only master_list
    if agent_list:
        compare_lists(master_list, agent_list)

    if public_agent_list:
        compare_lists(master_list, public_agent_list)


def check_duplicates(arg_list):
    assert isinstance(arg_list, list), 'only lists can be verified for duplicates'
    dups = list(filter(lambda x: arg_list.count(x) > 1, arg_list))
    assert not dups, 'List cannot contain duplicates: {}'.format(', '.join(set(dups)))


def compare_lists(first_list, second_list):
    assert isinstance(first_list, list), 'can compare only lists'
    assert isinstance(second_list, list), 'can compare only lists'
    dups = set(first_list) & set(second_list)
    assert not dups, 'master_list and agent_list cannot contain duplicates {}'.format(', '.join(dups))


def check_ipv4_addrs(ips):
    assert isinstance(ips, list)
    invalid_ips = []
    for ip in ips:
        try:
            socket.inet_pton(socket.AF_INET, str(ip))
        except OSError:
            invalid_ips.append(ip)
    assert not invalid_ips, ('Only IPv4 values are allowed. The following are invalid IPv4 addresses: '
                             '{}'.format(invalid_ips))


def validate_optional_agent(agent_list, public_agent_list):
    if agent_list:
        validate_hosts_list(agent_list, 'agent_list')

    if public_agent_list:
        validate_hosts_list(public_agent_list, 'public_agent_list')

    if agent_list and public_agent_list:
        compare_lists(agent_list, public_agent_list)


def run_validate_config(value_func_map, config, required=True):
    errors = {}
    for ssh_key, validate_func in value_func_map.items():
        input_value = config.get(ssh_key)
        if not input_value:
            if required:
                errors[ssh_key] = 'required parameter {} was not provided'.format(ssh_key)
            continue
        try:
            validate_func(input_value)
        except AssertionError as err:
            errors[ssh_key] = str(err)
    return errors


def validate_config(config):
    assert isinstance(config, dict)

    ssh_keys_checks_map_required = {
        'ssh_user': validate_ssh_user,
        'ssh_port': validate_ssh_port,
        'ssh_key_path': validate_ssh_key_path,
        'master_list': lambda master_list: validate_master_agent_lists(
            master_list,
            config.get('agent_list'),
            config.get('public_agent_list'))
    }
    ssh_keys_checks_map_optional = {
        'agent_list': lambda agent_list: validate_optional_agent(agent_list, config.get('public_agent_list')),
        'public_agent_list': lambda public_agent_list: validate_optional_agent(
            config.get('agent_list'),
            public_agent_list)
    }

    errors = run_validate_config(ssh_keys_checks_map_required, config)
    errors.update(run_validate_config(ssh_keys_checks_map_optional, config, required=False))
    return errors
