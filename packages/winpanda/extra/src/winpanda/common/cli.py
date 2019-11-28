"""Panda package management for Windows.

Application CLI specification.
"""


class CLI_COMMAND:
    """CLI command set."""
    SETUP = 'setup'
    TEARDOWN = 'teardown'
    START = 'start'
    STOP = 'stop'


class CLI_CMDTARGET:
    """CLI command target scope."""
    PKGALL = 'pkgall'
    STORAGE = 'storage'


VALID_CLI_CMDTARGETS = [getattr(CLI_CMDTARGET, sname) for sname in
                        CLI_CMDTARGET.__dict__ if not sname.startswith('__')]


class CLI_CMDOPT:
    """CLI command options set."""
    CMD_NAME = 'command_name'
    CMD_TARGET = 'command_target'
    INST_ROOT = 'inst_root_dpath'
    INST_CONF = 'inst_conf_dpath'
    INST_PKGREPO = 'inst_pkgrepo_dpath'
    INST_STATE = 'inst_state_dpath'
    INST_VAR = 'inst_var_dpath'
    INST_CLEAN = 'inst_clean'
    MASTER_PRIVIPADDR = 'master_priv_ipaddr'
    LOCAL_PRIVIPADDR = 'local_priv_ipaddr'
    DSTOR_URL = 'dstor_url'
    DSTOR_PKGREPOPATH = 'dstor_pkgrepo_path'
    DSTOR_PKGLISTPATH = 'dstor_pkglist_path'
    DSTOR_DCOSCFGPATH = 'dstor_dcoscfg_path'
    DCOS_CLUSTERCFGPATH = 'dcos_clustercfg_path'


CLI_ARGSPEC = '''Panda package management for Windows

Usage:
  winpanda {cmd_setup} [options]
  winpanda {cmd_teardown} [options]
  winpanda {cmd_start} [options]
  winpanda {cmd_stop} [options]

Options:
  --target=<target>                 target operational scope for a command
                                    (choose from: {valid_cmd_targets})
                                    [default: {default_cmd_target}]
  --inst-root-dir=<path>            DC/OS installation root directory
                                    [default: {default_root_dpath}]
  --inst-config-dir=<path>          DC/OS installation configuration directory
                                    [default: {default_config_dpath}]
  --inst-state-dir=<path>           DC/OS installation state directory
                                    [default: {default_state_dpath}]
  --inst-repo-dir=<path>            DC/OS local package repository directory
                                    [default: {default_repository_dpath}]
  --inst-var-data-dir=<path>        DC/OS variable data root directory
                                    [default: {default_var_dpath}]
  --clean                           Wipe out any leftovers from previous DC/OS
                                    installation before setting up a new one
  --master-priv-ipaddr=<ipaddr>...  master nodes private IP-addresses
                                    [default: ]
  --local-priv-ipaddr=<ipaddr>      agent node private IP-address
                                    [default: ]
  --dstor-url=<url>                 DC/OS distribution storage URL
                                    [default: ]
  --dstor-pkgrepo=<path>            DC/OS distribution storage package
                                    repository path
                                    [default: ]
  --dstor-pkglist=<path>            DC/OS distribution storage reference
                                    package list path
                                    [default: ]
  --dstor-dcoscfg=<path>            DC/OS distribution storage aggregated DC/OS
                                    configuration object path
                                    [default: ]
  --cluster-cfgfile=<path>          DC/OS cluster configuration options local
                                    file path
                                    [default: {default_clustercfg_fpath}]
'''
