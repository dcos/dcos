# Activating Packages `pkgpanda activate`

The list if currently active packages is stored in 'active.json' inside of INSTALL_ROOT.

active.json is swapped out when old packages are disabled and new ones are
enabled.

TODO(cmaloney): Define the requirements for a system image / how things are loaded. Ex:

```
mesos-slave.service must
EnvironmentFile=--/opt/mesosphere/environment
EnvironmentFile=/opt/mesosphere/config/mesos-slave-config
```

## Activating new packages

1. Validate new list of packages to activate has no conflicts
   - No conflicting provides
   - No conflicting systemd names
   - No conflicting executable names
   - No conflicting environment variables
1. Archive old packages
   - mv active.json active.json.old
   - rm -rf INSTALL_ROOT/bin INSTALL_ROOT/systemd INSTALL_ROOT/environment INSTALL_ROOT/config
1. Write new active manifest to active.json.new
1. Install new package config
  - Symlink binaries for every pacakge into INSTALL_ROOT/bin
  - Symlink config for each package into INSTALL_ROOT/config/{provides}/
  - Aggregate environment variables to INSTALL_ROOT/environment
1. Enable everthing in systemd

Note: Starting/stopping services is the job of the restart helper or rebooting the machine.

First active.json is moved to active.json.old, then all of the old
packages have their symlinks removed (INSTALL_ROOT/bin, INSTALL_ROOT/systemd,
  INSTALL_ROOT/environment, INSTALL_ROOT/config).


## Sample active.json
```
[
  "mesos--0.22.0",
  "mesos-config-1",
  "mesos-systemd-12"
]
```
