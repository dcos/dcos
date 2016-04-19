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

# Doing a local build

## Requirements

 - Linux
 - Docker (1.9+)
 - SELinux disabled
 - Python 3 as /usr/bin/python

## Steps

Create a config file based on config/dcos-release.config.yaml.
  - AWS, Azure, and Local storage are supported. See https://github.com/dcos/dcos/tree/master/release/storage.

Local storage example:
```
storage:
  local:
    kind: local_path
    path: /artifact-storage/
options:
  preferred: local
```


Setup a local build environment:
1. Make a python virtualenv `pyvenv ../env`
1. Activate the environment `source ../env/bin/activate`
1. Install dcos-image python to the environment as editable packages `./prep_local`

Doing a release build:
`release create <release-name> <tag>` where <release-name> is something like your name (cmaloney), tag lets you see what the build was from on pages like aws.html.


# TODO

Lots of docs are still being written. If you have immediate questions please ask the [DC/OS Community](https://dcos.io/community/). Someone else probably has exactly the same question.

 - Add getting started on common distros / dependencies
 - Add overview of what is in here, how it works
 - Add general theory of stuff that goes in here.
 - Setting up / using tox for dev
 - PR (guidelines, testing)
 - Running your first build
 - How to make different sorts of common changes
