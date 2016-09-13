import os
import stat

import gen


def validate_ssh_key_path(ssh_key_path):
    assert os.path.isfile(ssh_key_path), 'could not find ssh private key: {}'.format(ssh_key_path)
    assert stat.S_IMODE(
        os.stat(ssh_key_path).st_mode) & (stat.S_IRWXG + stat.S_IRWXO) == 0, (
            'ssh_key_path must be only read / write / executable by the owner. It may not be read / write / executable '
            'by group, or other.')
    with open(ssh_key_path) as fh:
        assert 'ENCRYPTED' not in fh.read(), ('Encrypted SSH keys (which contain passphrases) '
                                              'are not allowed. Use a key without a passphrase.')


def compare_lists(first_json: str, second_json: str):
    first_list = gen.calc.validate_json_list(first_json)
    second_list = gen.calc.validate_json_list(second_json)
    dups = set(first_list) & set(second_list)
    assert not dups, 'master_list and agent_list cannot contain duplicates {}'.format(', '.join(dups))


def validate_agent_lists(agent_list, public_agent_list):
    compare_lists(agent_list, public_agent_list)


entry = {
    'validate': [
        lambda agent_list: gen.calc.validate_ip_list(agent_list),
        lambda public_agent_list: gen.calc.validate_ip_list(public_agent_list),
        lambda master_list: gen.calc.validate_ip_list(master_list),
        # master list shouldn't contain anything in either agent lists
        lambda master_list, agent_list: compare_lists(master_list, agent_list),
        lambda master_list, public_agent_list: compare_lists(master_list, public_agent_list),
        # the agent lists shouldn't contain any common items
        lambda agent_list, public_agent_list: compare_lists(agent_list, public_agent_list),
        validate_ssh_key_path,
        lambda ssh_port: gen.calc.validate_int_in_range(ssh_port, 1, 32000),
        lambda ssh_parallelism: gen.calc.validate_int_in_range(ssh_parallelism, 1, 100)
    ],
    'default': {
        'ssh_key_path': 'genconf/ssh_key',
        'agent_list': '[]',
        'public_agent_list': '[]',
        'ssh_port': '22',
        'process_timeout': '120',
        'ssh_parallelism': '20'
    }
}

parameters = {
    'variables': {
        'ssh_user',
        'ssh_port',
        'ssh_key_path',
        'master_list',
        'agent_list',
        'public_agent_list',
        'ssh_parallelism',
        'process_timeout'
    }
}


def get_config_target():
    config_target = gen.ConfigTarget(parameters)
    config_target.add_entry(entry, False)
    return config_target


# TODO(cmaloney): Work this API, callers until this result remapping is unnecessary
# and the couple places that need this can just make a trivial call directly.
def validate_config(user_arguments):
    user_arguments = gen.stringify_configuration(user_arguments)
    messages = gen.validate_config_for_targets([get_config_target()], user_arguments)
    if messages['status'] == 'ok':
        return {}

    # Re-format to the expected format
    # TODO(cmaloney): Make the unnecessary
    final_errors = dict()
    for name, message_blob in messages['errors'].items():
        final_errors[name] = message_blob['message']
    return final_errors
