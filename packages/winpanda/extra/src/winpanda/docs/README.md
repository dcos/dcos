# Winpanda The DC/OS Windows Package Manager

## Major features

* Adds and manage windows node of DC/OS cluster.
  * Performs package management.
  * Config management.
  * Variable substitution in config file
  * Orchestrating NSSM service wrapper.
  * Logging Setup, Start, Upgrade operations of windows node.
  * Managing DC/OS for windows on disk file structure.
  * Handling Windows environment variables for DC/OS windows cluster node

## Command line parameters

### Usage

```text
  winpanda {setup} [options]
  winpanda {start} [options]
  winpanda {stop} [options]
```

### Commands

* Setup - This command performs the following steps in sequence:
    1. Reads `cluster.conf` from `etc` folder of `inst_root` looks for bootstrap node configuration there.
    2. Then downloads packages.
    3. Unpacks to filesystem.
    4. Makes substitution of `dcos-config-windows.yaml`.
    5. Executes extra and NSSM config files.
* Start - starts MSSM and SC services.
* Stop - stops all dcos services.

### Options

|Option|Argumrnts|Description|
|----|----|----|
| --target=|`storage, pkgall`|target operational scope for a command|
||`storage`|Creates fresh file structure only with autocleanup|
||`pkgall`|Performs full packages setup (includes `storage`)|
|--inst-root-dir=|`path`|DC/OS installation root directory [default: {default_root_dpath}]|
|--inst-config-dir=|`path`|DC/OS installation configuration directory [default: {default_config_dpath}]|
|--inst-state-dir=|`path`|DC/OS installation state directory [default: {default_state_dpath}]|
|--inst-repo-dir=|`path`|DC/OS local package repository directory [default: {default_repository_dpath}]|
|--inst-var-data-dir=|`path`|DC/OS variable data root directory [default: {default_var_dpath}]|
|--clean|TBD|Wipe out any leftovers from previous DC/OS installation before setting up a new one|
|--master-priv-ipaddr=|`ipaddr`|master nodes private IP-addresses [default: ]|
|--local-priv-ipaddr=|`ipaddr`|agent node private IP-address [default: ]|
|--dstor-url=|`url`|DC/OS distribution storage URL [default: ]|
|--dstor-pkgrepo=|`path`|DC/OS distribution storage package repository path [default: ]|
|--dstor-pkglist=|`path`|DC/OS distribution storage reference package list path [default: ]|
|--dstor-dcoscfg=|`path`|DC/OS distribution storage aggregated DC/OS configuration object path [default: ]|
|--cluster-cfgfile=|`path`|DC/OS cluster configuration options local file path [default: {default_clustercfg_fpath}]|

## File structure


DC/OS installation local storage management tools.

Default local storage layout for DC/OS installation:

```bash
<inst_drive>:/              # DC/OS installation drive
    └──<inst_root>             # DC/OS installation root dir
    ├──<inst_cfg>           # DC/OS installation config dir
    ├──<inst_pkgrepo>       # DC/OS local package repository dir
    ├──<inst_state>/        # DC/OS installation state dir
    │     └── <pkgactive>   # DC/OS active packages index
    │──<inst_var>/          # DC/OS installation variable data root dir
    │    ├──<inst_work>     # Package-specific work dirs
    │    ├──<inst_run>      # Package-specific/common runtime data
    │    ├──<inst_log>      # Package-specific/common log files
    │    └──<inst_tmp>      # Package-specific/common temporary data
    ├──<inst_bin>           # DC/OS installation shared executables dir
    └──<inst_lib>           # DC/OS installation shared libraries dir
```

## Pakage structure

```bash
<pkg name><Guid>/
  ├──bin                     # Package binnaries folder
  ├──conf                    # Package config templates folder
  ├──lib                     # More related to Linux but may include package sharable libs
  └──include                 # Aditional package files.
```

## cluster.conf

**cluster.conf** file contains data that winpanda uses for windows node setup in **INI** format
Example:

```ini
[master-node-1]
PrivateIPAddr=172.16.15.90
ZookeeperListenerPort=2181

[distribution-storage]
RootUrl=http://172.16.15.186:8080/2.1.0/genconf/serve
PkgRepoPath=windows/packages
PkgListPath=windows/package_lists/latest.package_list.json
DcosClusterPkgInfoPath=cluster-package-info.json

[local]
PrivateIPAddr=172.16.15.248
```

Default location is in

```text
<inst_drive>:/<inst_root>/<inst_cfg>/
```

Also it can be set with **--cluster-cfgfile** option

## Usage cases

### Run winpanda setup

## Appendix

* [Placeholders](PLACEHOLDERS.md)
* [Pkgpanda docs](../../../../../../pkgpanda/docs/readme.md)
