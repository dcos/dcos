# Packaging software

Pkgpanda packages are tarballs, containing (optionally) a metadata file `pkginfo.json` as well as several well-known directories. See [Package Concepts](package_concepts.md) for a full listing, as well as descriptions of what each should be used for.

They are always extracted and run from a predictable location. The prefix is always `/opt/mesosphere/{name}-{id}/` where name is the package name. This is effectively the PREFIX of the installed package in autotools terms. A package may rely on the absolute path to the package contents remaining constant.

Only one package of a given package name may be able to be active on a system at a time. If a package is not active, then there is no guarantee that the package is available on the machine, and files in it should not be referenced.

Pkgpanda operates by swapping out (roughly atomically) one set of active packages for another. If the health-checks of critical components fail after the swapping out, Pkgpanda will attempt to revert (Just another moving of directories), and restart the services again.

There are two

## Package build environment

See: [buildinfo.json](buildinfo.json.md)

 - Environment variables
 - Package directories
 -

# TODO
LD_LIBRARY_PATH, PATH, roles (bin_slave, bin_master)

# Guiding principles when packaging

 - Depend on as tight of a package version as you can, and only share things when necessary.

# Comon Tasks

## Providing other packages

If a package can depend on this exact version (mesos-config version x depends on mesos 0.22.0), then there is nothing which needs to be done, and the package can depend on the exact, predictable path of that file when unpacked as part of the package (And specify a dependency on the full package-id).

If the other packages which will use the file can know about the package name of the package which

If the file needs to be generally available to other packages which don't know what

## Depending on other packages

## Adding

## Multiple versions of the same logical package

If there is one upstream package which you need
protbuf-2.5.0-1

This works because

# Unsupported items

## Language-specific packages

Currently packagepanda has no clue how, for instance,

## Users

Currently there isn't a good way of reliably adding users on a large number of machines which have had potentially non-identical config applied to them. Pkgpanda in a future release will utilize [Systemd Sysusers](http://www.freedesktop.org/software/systemd/man/systemd-sysusers.html) or something similar to provide the ability to manage users on a machine.


## Fine-grained dependencies

Not currently implemented. Eventually a package will be able to give the list of things it needs in it's operating environment (libraries, executables in path, files on filesystem, users). This is a much more robust way to state dependencies (At the cost of increased complexity, but the computation is still less than a second).


## Depending on other packages



Often ther



Every package is ide

Pkgpanda reliably ex

Every package lives in isolation from other packages, and can be installed/uninstalled
atomically. There is no notion of being able to edit things



Packages are unpacked to

a metadata file `pkginfo.json`, and


Every package has a *Package Name* as well as a *Package Id*. Packages are unpacked
to predictable locations so they may

The `pkginfo.json` contains

Packages depending on eachother. S


There
are several well known directories in the tarball

bin/
lib/
etc/
dcos.target.wants

environment variables, conflicts

Dependencies / requirements

Splitting up packages (mesos, master-config, mesos-config, etc)

tar -czf mesos--0.22.0.tar.xz -C mesos--0.22.0 .