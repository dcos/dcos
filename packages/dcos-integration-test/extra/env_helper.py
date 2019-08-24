import os
import sys

from typing import Dict

HELP_MESSAGE = """
QUICKSTART EXAMPLE

  {begin_cmd}ssh-add ~/.ssh/my_aws_key{end_cmd}
  {begin_cmd}export SSH_USER=centos{end_cmd}
  {begin_cmd}export MASTER_PUBLIC_IP=54.186.5.36{end_cmd}
  {begin_cmd}export WAIT_FOR_HOSTS=false{end_cmd}
  {begin_cmd}pytest -s -k test_root_path_http{end_cmd}


ALL ENVIRONMENT VARIABLES:

  Required variables

    {begin_color}DCOS_SSH_USER{end_color}
    Ssh user for your Cluster.

    {begin_color}MASTER_PUBLIC_IP{end_color}
    Public IP of the master to run tests on.

    \033[93mIf waiting for all hosts to be registered is not
    important for your case, you can set WAIT_FOR_HOSTS=false
    and skip the three variables below.\033[0m

    {begin_color}PUBLIC_AGENTS_PRIVATE_IPS{end_color}
    Comma-separated list of public agent private IPs.

    {begin_color}PRIVATE_AGENTS_PRIVATE_IPS{end_color}
    Comma-separated list of private agent private IPs.

    {begin_color}MASTERS_PRIVATE_IPS{end_color}
    Comma-separated list of master private IPs.


  Required variables for DC/OS Enterprise only

    {begin_color}DCOS_LOGIN_UNAME{end_color}
    DC/OS username for logging into your cluster.

    {begin_color}DCOS_LOGIN_PW{end_color}
    DC/OS password for logging into your cluster.


  Optional variables

    {begin_color}DCOS_ACS_TOKEN{end_color}
    For DC/OS Open only.
    Obtain this token by setting up your cluster with the dcos-cli like this:
    {begin_cmd}dcos cluster setup $MASTER_PUBLIC_IP{end_cmd}
    Then your web browser will open a page and you will see the token.
    It's also stored in ~/.dcos/clusters/<cluster-uuid>/dcos.toml
    If you run integration tests before setting this variable, you will
    no longer be able to log into your cluster.

    {begin_color}DCOS_SSH_KEY_PATH{end_color}
    Full path to the private key for your cluster.
    If not set, you must add the key to your ssh agent.
""".format(begin_color='\u001b[38;5;42m', end_color='\u001b[0m', begin_cmd='\033[0;30;47m', end_cmd='\033[0m')

# We use different variable names than inside the cluster to not confuse the user.
# For example, it's not clear if PRIVATE_AGENTS_PRIVATE_IPS are public or private agents, public ips or private ips
ENV_VAR_MAPPINGS = {
    'MASTERS_PRIVATE_IPS': 'MASTER_HOSTS',
    'PUBLIC_AGENTS_PRIVATE_IPS': 'PUBLIC_SLAVE_HOSTS',
    'PRIVATE_AGENTS_PRIVATE_IPS': 'SLAVE_HOSTS'
}


def print_red(text: str) -> None:
    start = '\033[91m'
    end = '\033[0m'
    print(start + text + end)


def print_yellow(text: str) -> None:
    start = '\033[93m'
    end = '\033[0m'
    print(start + text + end)


def set_required_env_var(dcos_env_vars: dict, env_var_name: str) -> None:
    env_var = os.getenv(env_var_name)
    if env_var is None:
        print_red("ERROR: required environment variable '{}' is not set!".format(env_var_name))

        if not dcos_env_vars:
            print_red('No dcos-test-utils variables were detected in your environment.')
        else:
            print('Current dcos-test-utils variables detected in your environment:')
            for k, v in dcos_env_vars.items():
                print('{}={}'.format(k, v))

        print_red("Run 'pytest --env-help' to see all environment variables to set.")
        sys.exit(1)

    dcos_env_vars[env_var_name] = env_var


def load_env_vars() -> Dict[str, str]:
    dcos_env_vars = {}  # type: Dict[str, str]
    required_env_vars = ['DCOS_SSH_USER', 'MASTER_PUBLIC_IP']
    non_required_env_vars = ['DCOS_LOGIN_UNAME', 'DCOS_LOGIN_PW', 'DCOS_ACS_TOKEN', 'DCOS_SSH_KEY_PATH']
    wait_for_hosts = os.getenv('WAIT_FOR_HOSTS', 'true')
    if wait_for_hosts == 'true':
        required_env_vars += ['PUBLIC_AGENTS_PRIVATE_IPS', 'PRIVATE_AGENTS_PRIVATE_IPS', 'MASTERS_PRIVATE_IPS']
    else:
        dcos_env_vars['WAIT_FOR_HOSTS'] = 'false'

    for e in non_required_env_vars:
        v = os.getenv(e)
        if v:
            dcos_env_vars[e] = v

    for e in required_env_vars:
        set_required_env_var(dcos_env_vars, e)

    for k, v in ENV_VAR_MAPPINGS.items():
        if k in dcos_env_vars:
            dcos_env_vars[v] = dcos_env_vars[k]
            del dcos_env_vars[k]

    return dcos_env_vars


def get_env_vars() -> Dict[str, str]:
    env_vars = load_env_vars()
    if 'DCOS_SSH_KEY_PATH' not in env_vars:
        print_yellow("Environment variable 'DCOS_SSH_KEY_PATH' is not set. Make sure you add the ssh key for your "
                     "cluster to your ssh agent!")
    return env_vars
