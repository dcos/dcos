# DC/OS Tools, Packages, and Installers for various platforms

Tools for building DC/OS and launchign a cluster with it in the hardware of a customer's choice.

  - *docker/* Locally defined docker containers packages are built in
  - *docs/* Documentation
  - *ext/dcos-installer/* Backend for Web, SSH, and some bits of the Advanced installer. To be merged into the top codebase once the code is cleaned up
  - *gen/* Python library for rendering yaml config files for various platforms into packages, with utilities to do things like make "late binding" config set by CloudFormation
  - *gen/installer/* Code to take a build and transform it into a particular platform installer (Bash / command line, AWS, Azure, etc.)
  - *packages/* Packages which make up DC/OS (Mesos, Marathon, AdminRouter, etc). These packages are built by pkgpanda, and combined into a "bootstrap" tarball for deployment.
  - *pkgpanda/* DC/OS baseline/host package management system. Tools for building, deploying, upgrading, and bundling packages together which live on the root filesystem of a machine / underneath Mesos.
  - *pytest/* Misc. tests. Should be moved to live next to the appropriate code
  - *release/* Release tools for DC/OS. (Building releases, building installers for releases, promoting between channels)
  - *ssh/* AsyncIO based parallel ssh library used by the installer
  - *test_util/* various scripts, utilties to help with integration testing

All code in this repository is Python 3


# TODO

Lots of docs are still being written. If you have immediate questions please ask the [DC/OS Community](https://dcos.io/community/). Someone else probably has exactly the same question.

 - Building locally
 - Add getting started on common distros / dependencies
 - Add overview of what is in here, how it works
 - Add general theory of stuff that goes in here.
 - Setting up / using tox for dev
 - PR (guidelines, testing)
 - Running your first build
 - How to make different sorts of common changes
