# Pkgpanda: The DC/OS Package Manager

Most packages run in containers on top of Mesos, using its native mechanism. There are requirements to install and run
packages on top of the host system.

`pkgpanda` allows for having multiple versions of every component present on a host and selecting one of them to
be active at a given time.

# Major features

1. Ability to have multiple versions of a package ready for use simultaneously on a host.
2. No notion of modifying existing state. A package is either active (all it's is state alive), or not.

# Documentation

* [For Packagers](for_packagers.md)
* [Package Concepts](package_concepts.md)

# Internals

* [Filesystem Layout](filesystem_layout.md)
* [Activating Packages](activating.md)

# WIP / long term design

* [Architecture for Cluster Upgrades](architecture.md)
* [Deployer component](deployer.md)
* [Modules](modules.md)
