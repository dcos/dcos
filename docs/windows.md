---
post_title: >
    Design: Installation (Windows)
nav_title: Installation (Windows)
menu_order: 5
---
- *Note: This is a description of a feature in progress. In order to see the status of specific changes, please refer to* [Way Forward](#way-forward)

The installation design of DC/OS on linux and linux-like systems is covered in [docs](https://dcos.io/docs/overview/design/installation/). 
Build, installation and update The windows environment necessitates a number of changes to that design.
- Windows has no native support tar files, but does for zip file.
- Windows does not have native support for bash, but does for powershell.
- Windows does not have native support for utilities like curl, wget, grep, awk, sed and the such, but does for near-equivelent powershell cmdlets which can fullfill the same function. 
- Windows does not support some os specific python modules, but has support for others. 
- There are differences between windows and linux/unix handle semantics and ioctls.
- There are differences in file system semantics and file system conventions (i.e, "/opt/mesosphere" vs "c:/Mesosphere")
- Windows does not support systemd or journald.
- Many of the packages used in the linux deployment are different in the windows environment.
- Windows machines usually depend on pre-built packages rather than in-situ builds from source.

## Design Goals

The deployment process for Windows must be significantly different form linux. The design goals of goals of the Windows deployment are:
- Make those differences as consistent and predictable as possible. In principle a linux DC/OS system administrator should be able to learn a few transformation rules between the two environments and predict how to install, modify and operate a Windows host using the same skills they have already developed in linux.
- Make the deployment also Windows native. A Windows sysadmin should be able to apply their knowlege hand habits as much as possible.
- Make the deployment functionally equivalent (so far as possible) to the linux deployment.  A DC/OS UI user should not be able to obviously tell the difference between a linux and windows host without looking at the host attributes.

The installation adds to those goals:
- The deployment should be feasible on a Windows host without additional preparation. As a result, the deployment must use only tools available on a freshly installed windows machine.


## Packaging

We chose zip files rather than tarballs for the packaging format because it works by default both on Windows and linux, without the necessity of installing something like cygwin or mingw64 tools. Like tarballs, zip files are a compressible file format that bundles a number of files together into a single archive. Clearly other packaging options are available, such as nuget packages, they are really just zipfiles under the covers. Unfortunately almost all the common formats are built around a single non-windows OS or language, requiring considerable effort in preparing a machine for installation, which in turn makes it more difficult to implement installation for all of the target environments (on-prem, azure, AWS, or others). Like the linux implementation, we simplify and made the package installation one step: zipfile extraction. Like linux, no arbitrary code execution and guaranteed reproducibility.

All of the components in DC/OS Windows are built into a single zip file that eventually gets extracted to `%SYSTEMDRIVE%:/Mesosphere` on the host system. Inside that directory, you end up with something that looks a lot like `/usr/local` on linux. Each component lives in its own package directory and then has the important files linked to the important directories like `bin` and `lib`.


## Building

Like linux, the master artifact must be assembled somehow. Because the DC/OS build is made up of a changing list of components, the build tooling ends up looking like its own little package manager. Each component must be built from source, configured in a repeatable fashion and then added into the master artifact.

A DC/OS package is defined by two files. In windows, these are powershell rather than bash scripts, but their function is identical: [`build.ps1`][1] and [`buildinfo.json`][2]. These state what must be downloaded and how to build it. At build time, the toolchain takes care of building, packaging and including all the artifacts required into the master zip file.

Because the dependent tools, packages, configuration, even formats are different between Windows and Linux, it is necessary to separately build the linux and windows packages on the respective systems.


## Installing

Now that there’s a single package containing all the built components to run DC/OS, each installation must be configured before being placed on hosts. By keeping this configuration small and immutable, you can be sure that every host in your cluster will act the same way.

With the configuration tool, all components are built into a package that contains everything to get the cluster running. You’ll pick from a small list of details like DNS configuration and bootstrap information. This then gets added to the single tarball that was built previously. You then have a package that is customized for your hardware and will repeatably create clusters of any size over and over.

Orchestrating the rollout of an installation is difficult, particularly when you are required to do things in a specific order. To keep everything as simple as possible, at the host level DC/OS makes no assumptions about the state of the cluster. You can install agents and then masters or even install both at the same time!

Once your package is built, you can get going by running `dcos_install.sh` on every host. This script only does three things:

- Downloads the package to the current host.
- Extracts the package into `/opt/mesosphere`.
- Initiates installation using the [DC/OS Component Package Manager (Pkgpanda)](/docs/1.11/overview/architecture/components/#dcos-component-package-manager).

That’s really it! Once the ZooKeeper cluster reaches quorum on the masters and Mesos comes up, every agent will join the cluster and you’ll be ready to go. We’ve kept the steps minimal to make sure they’re as reliable as possible.


## Tradeoffs

Obviously, there are other ways that this could have been architected. Let us take a look at some of the common questions and why the current decisions were made.


## Immutable Configuration

The configuration for each cluster is generated at the beginning and becomes immutable. This allows us to guarantee that the configuration is correct on every host after install. Remember, you will be doing this for thousands of nodes. These guarantees around configuration reduce the amount of documentation required to run DC/OS and make it more easily supportable.

With an immutable configuration, there is no chance of a host getting part of its configuration updated / changed. Many of the production issues we’ve encountered are ameliorated by this design decision. Take a look at Joe Smith’s presentation on [Running Mesos in Production at Twitter](https://www.youtube.com/watch?v=nNrh-gdu9m4) if you’d like more context.

### What IP should I bind to?

Deciding the IP and network interface that has access to the network and the Mesos master is non-trivial. Here are examples of environments that we cannot make default assumptions in:

- In split horizon environments like AWS, the hostname might resolve to an external IP address instead of internal.
- In environments without DNS, we need you to tell us what IP it is.
- In environments with multiple interfaces, we’re unable to automatically pick which interface to use.
- Not all machines have resolvable hostnames, so you can’t do a reverse lookup

Because of these constraints, we’ve struggled to produce a solid default. To make it as configurable as possible, we have a script that can be written to return the IP address we should bind to on every host. There are multiple examples in the documentation of how to write `ip-detect` for different environments which should cover most use cases. For those that the default doesn’t work, you will be able to write your own `ip-detect` and integrate it with your configuration. `ip-detect` is the most important part of the configuration and the only way your clusters will be able to come up successfully.

### Single vs. Multiple Packages, Per-Provider Packages (RPM, DEB, etc)

Instead of having all the packages bundled together into a single image, we could have gone the default route that most use today and install them all separately. There are a couple problems that come from this immediately:

- Moving between distributions requires porting and testing the packages.
- Package installs have non-zero failure rates. We have seen 10-20% failure rates when trying to install packages. This prevents the cluster coming up successfully and makes it harder to operate.
- Shipping multiple packages is far more difficult than having a single tarball to hand out. There’s overhead in ensuring multiple packages are robust.
- Upgrades must be atomic. It is much more difficult to ensure this across multiple packages.

### Tarball vs. Container

It would be possible to package DC/OS as a plethora of containers (or a single container with multiple processes). This combines the drawbacks of multiple packages with the instability of the Docker daemon. We’ve found that the Docker daemon crashes regularly and while that is acceptable for some applications, it isn’t something you want from the base infrastructure.

### Installation Method

We could support any installation method under the sun. The plethora of configuration and package management that is currently used is intimidating. We’ve seen everything from Puppet to custom built internal tools. We want to enable these methods by providing a simple interface that works with as many tools as possible. The lowest common denominator here is bash.

As it is difficult to maintain bash, we simplified the installation method as far as possible. The “image” that is built can be placed on top of a running host and operate independently. To install this, it only requires extraction. That’s a small, simple bash script that can work everywhere and integrate easily with other tooling. The entire exposed surface is minimal, and doesn’t give access to internals which if changed would make your cluster unsupportable and void the warranty.

### Host Images

It is possible to bake an entire host image that has been configured instead of a tarball that goes on top. Let’s look at why this doesn’t make sense as the sole method for installation:

- We end up being in the distribution update game. Every time RHEL releases a package update, we would be required to test, bundle and distribute that. This becomes even harder with CoreOS as we’d end up actually forking the project.
- You want to choose their distribution. Some have existing support contracts with Canonical and some with RedHat.
- You want to configure the base OS. There are security policies and configuration that must be applied to the host.

Host images are a great way to distribute and install DC/OS. By providing the bash install method, it is just as easy to create a new host image for your infrastructure as it would be to integrate with a tool like Puppet.

### Exposing config files directly to the user

The components included in DC/OS have a significant amount of configuration options. We have spent a long time piecing the correct ones together. These are guaranteed to give you the best operations in production at scale. If we were to expose these options, it would increase the amount of knowledge required to run an DC/OS cluster.

Remember that clusters most look almost the same for package install to work. As soon as configuration parameters that the frameworks rely on change, we cannot guarantee that a package can install or run reliably.

## Way Forward

### Specific Modifications Required

### Current Status


[1]: https://github.com/dcos/dcos/blob/master/packages/mesos/build
[2]: https://github.com/dcos/dcos/blob/master/packages/mesos/buildinfo.json
