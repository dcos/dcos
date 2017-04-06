# Package Basics
DC/OS uses a custom packaging tool called [pkgpanda](../pkgpanda) which operates on a "package tree". The [packages](../packages) directory is the root of all the packages and `pkgpanda` is built to construct it into a "package tree". A "package tree" is constructed by looking in each directory in a root and parsing a `buildinfo.json` and `build` file from each directory. If these are present, then the directory is considered a package and added to the tree. This tool can read these metadata JSONs in a "package tree", verify the package dependency list is resolvable by walking through dependent packages, and then use the build script files accompanying the metadata to actually build and export the package. For more information on why these design choices were made, take a look at the [docs](https://dcos.io/docs/overview/design/installation/).

In addition, pkgpanda performs a few other critical functions:
* Under the hood of a DC/OS deployment, `pkgpanda` is also responsible for managing the symlinks and filepaths that will link artifacts to the runtime environment of the host system.
* In each build, the artifacts for every package are cached either locally or on a 3rd party storage provider (AWS and Azure). This greatly reduces build time as most DC/OS changes only touch one independent package at a time. The artifacts include sources so if a 3rd party source should ever suddenly disappear, there will be a reliable backup.
* Package builds are isolated. By performing builds in a docker container, all sources and dependencies must be explicitly declared.

The packages built by pkgpanda make up the core set of components that comprise DC/OS. However, to actually spawn a DC/OS instance, tools must be built with baked-in configurations to deploy the specific set of artifacts to a given provider (generic term for any entity providing hardware on which DC/OS will run). For this, DC/OS has a script called [release](../release). Its function is:
* ingesting the completed build artifacts and parsing their metadata
* rendering deploy templates with references to the artifacts
* bundling the installer with the artifacts
* uploading everything to remote hosting services (S3 or Azure). Templates and the onprem installer are the current deploy methods native to DC/OS, but in theory a new form of provider could be implemented by adding a new module to the [provider tools](../gen/build_deploy).
