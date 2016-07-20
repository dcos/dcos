# Packaging software

`pkgpanda packages` are tarballs, containing (optionally) a metadata file `pkginfo.json` as well as several well-known
directories. See [Package Concepts](package_concepts.md) for a full listing, as well as descriptions of each section.
should be used for.

Packages are always extracted and run from a predictable location. The standard prefix is
`/opt/mesosphere/{name}-{id}/` where `{name}` is the package name and `{id}`, a id associated with the package . This
is effectively the `PREFIX` of the installed package in the `autotools` terms. A package may rely on the absolute path
to the package contents to remaining constant.

Only one package of a given package name may be active on a system at a given time. If a package is not active, then
there is no guarantee that the package is available on the machine, and files in it should not be referenced.

Pkgpanda operates by swapping out (roughly atomically) one set of active packages for another. If the health-checks of
critical components fail while swapping out, Pkgpanda will attempt to revert (another move of directories), and restart
the services again.

## Package build environment

The package build environment is described in [buildinfo.json](buildinfo.json.md). It has

* Environment variables
* Package directories

# Guiding principles when packaging

* Depend upon a specific version if you can, and only share things when necessary.

# Common Tasks

## Providing other packages

If a package can depend upon an exact version like `mesos-config version x` depends on `mesos 0.22.0`, then there is
nothing which needs to be done, and the package can depend on the exact, predictable path of that file when unpacked as
part of the package. It can specify the dependency on the full package-id.

# Depending on other packages

## Adding Multiple versions of the same logical package

If there is one upstream package which you need, this can be specified explicitly

* `protbuf-2.5.0-1`

# Unsupported items

## Language-specific packages

*Not currently implemented*

## Users

*Not currently implemented*

There isn't a good way of reliably adding users on a large number of machines which have had potentially non-identical
config applied to them. Pkgpanda in a future release will utilize [Systemd Sysusers] or something similar to provide
the ability to manage users on a machine.

## Fine-grained dependencies

*Not currently implemented.*

Eventually a package will be able to give the list of things it needs in it's operating environment (libraries,
executables in path, files on filesystem, users). This is a much more robust way to state dependencies (At the cost of
increased complexity, but the computation is still less than a second).

## Depending on other packages

Every package lives in isolation from other packages, and can be installed/uninstalled atomically.

Packages are unpacked to a metadata file `pkginfo.json`, and Every package has a *Package Name* as well as a *Package
Id*. Packages are unpacked to predictable locations so they may reference the absolute path to the file.

The `pkginfo.json` contains Packages depending on each other.

**Well Known Directories**

There are several well known directories in the tarball

```bash
bin/
lib/
etc/
dcos.target.wants
```

# TODO

* `LD_LIBRARY_PATH`
* `PATH`
* `roles` - `bin_slave`, `bin_master`
* Splitting up packages (mesos, master-config, mesos-config, etc)
* Document package environment variables, conflicts, and dependencies / requirements

[Systemd Sysusers]: http://www.freedesktop.org/software/systemd/man/systemd-sysusers.html
