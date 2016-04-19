# Pkgpanda: The DC/OS Package manager

While most things can run in containers on top of mesos, using whatever fetching mechanism

# Major features

1. Ability to have multiple versions of a package ready for use simultaneously on a host.
2. No notion of modifying existing state. A package is either active (all its state alive), or not.

# Documentation

[For Packagers](for_packagers.md)
[Package Concepts](package_concepts.md)


# Internals
[Filesystem Layout](filesystem_layout.md)
[Activating Packages](activating.md)

# WIP / long term design

[Architecture for Cluster Upgrades](architecture.md)
[Deployer component](deployer.md)
[Modules](modueles.md)
