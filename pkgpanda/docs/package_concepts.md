# Package concepts

*Package Name*

The name which other packages will know this package by and use. Package names must be valid Linux folder names, should
be case insensitive most often lower case only. Valid characters are `[a-zA-Z0-9@._+-]`. They may not start with a hyphen
or a dot. Must be at least one character long. A package name may not contain '--'.

*Package ID*

`name--version` combination package name + arbitrary information (most often a version indicator). The packaging system needs to extract the package name from a package id. Valid characters are `[a-zA-Z0-9@._+-]`

*pkginfo.json*

Metadata file containing the requirements of the package (either package names or package ids), as well as the
environment variables provided by the package.

pkginfo.json also stores all the sysctl requirements that are collected from buildinfo.json

For e.g. `dcos-net`'s pkginfo will have this information which is collected the packages buildinfo.json

```bash
{
  "sysctl": {
      "dcos-net": {
          "net.netfilter.nf_conntrack_tcp_be_liberal": "1",
          "net.netfilter.ip_conntrack_tcp_be_liberal": "1",
          "net.ipv4.netfilter.ip_conntrack_tcp_be_liberal": "1"
      }
  }
}
```

* It denotes the `sysctl` required for the *service-name* `dcos-net`

These configuration settings are accumulated for all packages in a file
`/opt/mesosphere/etc/dcos-service-configuration.json`, and the dcos bootstrap process will apply these settings before
starting the service.

*Well-known directories*

Every pkgpanda package may put items in several well-known directories within the package to have them available to other packages globally via symlinks.

```bash
lib/  # Will be linked to /opt/mesosphere/lib
bin/  # Will be linked to /opt/mesosphere/bin
etc/  # Will be linked to /opt/mesosphere/etc
dcos.target.wants/  # Will be linked into /etc/systemd/system/dcos.target.wants
```

Each of these directories can be appended with an underscore and a role name, which will cause the files to only be linked on nodes of those role type. E.G. `$PKG_PATH/etc_master/` will only be linked on a master node.

## Install directories

The packaging system makes use of some *well-known directories*. Well-known directories are used so that packages can
find information from other packages without having to know the exact package version some piece is coming from.

## Package

Different things want to rely on finding individual packages at certain locations. When we unbundle packages, there are
often multiple components which are shipped independently (So, we can update Java without having to re-ship
everything).

In order, for all the java packages to find the "current Java" we need to make Java at a well-known location. There are
well-known directories which packages can depend on upon. All other filesystem directories should be assumed not to
exist.

### Why /opt/mesosphere/etc, etc.

Not all packages know what is going to provide bits of environment. Mesos shouldn't need to know for instance what is
the name of the package which provides `HDFS`, it just cares if `HDFS` is available.

This goes for config as well, we may want a specific monolithic `mesos-config` package name, or a bunch of small
`mesos-slave-config`, `mesos-master-config` packages. Either way Mesos needs to find the config.

### Special install files and directories

All the environment variables to be used when running Mesos are available at `/opt/mesosphere/environment`. Compiled
from a `environment` section in `pkginfo.json` of every active package, as well as a generated `PATH` and
`LD_LIBRARY_PATH` containing the `/opt/mesosphere/bin` and `/opt/mesosphere/lib` respectively.


```bash
/opt/mesosphere/bin/
/opt/mesosphere/lib/
/opt/mesosphere/etc/
/opt/mesosphere/active/{name}/
/opt/mesosphere/packages/{id}/
/etc/systemd/system/dcos.target.wants/
```

### Assumed system files

`/etc/systemd/system/multi-user.target/dcos.target`

### Reasoning

**Why don't we do /{name}/current ?**

  - Then we can't atomically swap things into place, easier to get partial updates.

**Why not make /{name}/{id_without_name} ?**

  - Who cleans up /{name}/?
  - Lots more logic to get wrong, coordination required.

**When things go wrong, how to recover**

1. Dump the host and load a new one, simplest safest
2. `pkgpanda setup` the host.
3. pkgpanda activate {list of packages}
    - Fix problems if they happen
