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

## Well-known directories

Packages may depend on files from other packages at runtime; e.g. Mesos reads config at startup that is provided by a
separate config package. But if the Mesos package is built to look for config inside the config package's directory,
that config package would need to exist before the Mesos package can be built, and generating a new config package
would require building a new Mesos package that looks for config at the new location. To eliminate this coupling,
Pkgpanda makes use of *well-known directories*. These are special directories in a package whose files are symlinked
from well-known locations accessible to other packages.

Package directory    | Files are symlinked from:
-------------------- | -------------------------
`bin/`               | `/opt/mesosphere/bin/`
`etc/`               | `/opt/mesosphere/etc/`
`lib/`               | `/opt/mesosphere/lib/`
`include/`           | `/opt/mesosphere/include/`
`dcos.target.wants/` | `/etc/systemd/system/dcos.target.wants/` (See **dcos.target.wants** below.)

If the config package writes its Mesos config file to `etc/mesos`, it'll be symlinked from `/opt/mesosphere/etc/mesos`,
where the Mesos package can find it. Because the Mesos package is looking for its config at this fixed location, a new
config package can be built and distributed without rebuilding the Mesos package.

Each of these special package directories can be appended with an underscore and a role name, which will cause the
files to only be linked on nodes of that role. E.g. files under the package directory `etc_master/` will only be linked
from `/opt/mesosphere/etc/` on a master node.

### dcos.target.wants

The package directory `dcos.target.wants/` is a well-known directory that's intended for systemd unit files, and the
files within are made available at `/etc/systemd/system/dcos.target.wants/`. However this well-known directory is
handled differently from the others due to requirements imposed by systemd: each symlink under
`/etc/systemd/system/dcos.target.wants/` must have a corresponding unit file at `/etc/systemd/system/`, and unit files
and their symlinks must be readable when systemd starts, potentially before it mounts the volume that contains the
package files. So when a package containing a `dcos.target.wants/` is activated on a cluster node, the files within are
copied to `/etc/systemd/system/`, and the symlinks under `/etc/systemd/system/dcos.target.wants/` point to those
copies. This allows systemd to start DC/OS units before it mounts the DC/OS installation.

## Special install files and directories

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

## Assumed system files

`/etc/systemd/system/multi-user.target/dcos.target`

## Reasoning

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
