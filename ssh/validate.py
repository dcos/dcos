import gen
from gen.internals import Source, Target


def compare_lists(first_json: str, second_json: str):
    first_list = gen.calc.validate_json_list(first_json)
    second_list = gen.calc.validate_json_list(second_json)
    dups = set(first_list) & set(second_list)
    assert not dups, 'master_list and agent_list cannot contain duplicates {}'.format(', '.join(dups))


def validate_agent_lists(agent_list, public_agent_list):
    compare_lists(agent_list, public_agent_list)


source = Source({
    'validate': [
        lambda agent_list: gen.calc.validate_ip_list(agent_list),
        lambda public_agent_list: gen.calc.validate_ip_list(public_agent_list),
        lambda master_list: gen.calc.validate_ip_list(master_list),
        # master list shouldn't contain anything in either agent lists
        lambda master_list, agent_list: compare_lists(master_list, agent_list),
        lambda master_list, public_agent_list: compare_lists(master_list, public_agent_list),
        # the agent lists shouldn't contain any common items
        lambda agent_list, public_agent_list: compare_lists(agent_list, public_agent_list),
        lambda ssh_port: gen.calc.validate_int_in_range(ssh_port, 1, 32000),
        lambda ssh_parallelism: gen.calc.validate_int_in_range(ssh_parallelism, 1, 100)
    ],
    'default': {
        'ssh_key_path': 'genconf/ssh_key',
        'agent_list': '[]',
        'public_agent_list': '[]',
        'ssh_user': 'centos',
        'ssh_port': '22',
        'process_timeout': '120',
        'ssh_parallelism': '20'
    }
})


def get_target():
    return Target({
        'ssh_user',
        'ssh_port',
        'ssh_key_path',
        'master_list',
        'agent_list',
        'public_agent_list',
        'ssh_parallelism',
        'process_timeout'})


# TODO(cmaloney): Work this API, callers until this result remapping is unnecessary
# and the couple places that need this can just make a trivial call directly.
def validate_config(user_arguments):
    user_arguments = gen.stringify_configuration(user_arguments)
    user_source = gen.user_arguments_to_source(user_arguments)
    messages = gen.internals.resolve_configuration([source, user_source], [get_target()]).status_dict
    if messages['status'] == 'ok':
        return {}

    # Re-format to the expected format
    # TODO(cmaloney): Make the unnecessary
    final_errors = dict()
    for name, message_blob in messages['errors'].items():
        final_errors[name] = message_blob['message']
    return final_errors
