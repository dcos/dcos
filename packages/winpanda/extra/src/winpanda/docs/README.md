# Winpanda The DC/OS Windows Package Manager

# Major features

# Documentation

## Command line parametres

```
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
```

## File structure

```text
DC/OS installation local storage management tools.

Default local storage layout for DC/OS installation:

<inst_drive>:/                # DC/OS installation drive
    +-<inst_root>/            # DC/OS installation root dir
        +-<inst_cfg>/         # DC/OS installation config dir
        +-<inst_pkgrepo>/     # DC/OS local package repository dir
        +-<inst_state>/       # DC/OS installation state dir
            +-<pkgactive>/    # DC/OS active packages index
        +-<inst_var>/         # DC/OS installation variable data root dir
            +-<inst_work>/    # Package-specific work dirs
            +-<inst_run>/     # Package-specific/common runtime data
            +-<inst_log>/     # Package-specific/common log files
            +-<inst_tmp>/     # Package-specific/common temporary data
        +-<inst_bin>/         # DC/OS installation shared executables dir
        +-<inst_lib>/         # DC/OS installation shared libraries dir
```

## Usage cases

## Apendix

* [Placeholders](PLACEHOLDERS.md)
* [Pkgpanda docs](../../../../../../pkgpanda/docs/readme.md)
# Internals
-------------------------------------------------------------------------------
