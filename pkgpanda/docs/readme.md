# Pkgpanda: The DC/OS Package Manager

`pkgpanda` allows for having multiple versions of every component present on a host and selecting one of them to
be active at a given time.

# Major features

1. Ability to have multiple versions of a package ready for use simultaneously on a host.
2. No notion of modifying existing state. A package is either active (all it's is state alive), or not.

# Documentation

* [For Packagers](create_and_maintain_packages.md)
* [Package Concepts](package_concepts.md)
* [Tree Concepts](tree_concepts.md)
* [HTTP API](http.md)

# Internals

* [Filesystem Layout](filesystem_layout.md)
* [Activating Packages](activating.md)
