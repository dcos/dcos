# DC/OS Tools, Packages, and Installers for various platforms

Tools for building DC/OS and launching a cluster with it in the hardware of a customer's choice.

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
  - *test_util/* various scripts, utilities to help with integration testing

All code in this repository is Python 3

# Doing a local build

## Dependencies
  1. Linux distribution:
    - Docker doesn't have all the features needed on OS X or Windows
    - `tar` needs to be GNU tar for the set of flags used
  1. [tox](https://tox.readthedocs.org/en/latest/)
  1. git
  1. Docker
    - [Install Instructions for varios distributions](https://docs.docker.com/engine/installation/). Docker needs to be configued so your user can run docker containers. The command `docker run alpine  /bin/echo 'Hello, World!'` when run at a new terminal as your user should just print `"Hello, World!"`. If it says something like "Unable to find image 'alpine:latest' locally" then re-run and the message should go away.
  1. Python 3.4
    - Arch Linux: `sudo pacman -S python`
    - Fedora 23 Workstation: Already installed by default / no steps
  1. Over 10GB of free disk space
  1. _Optional_ pxz (speeds up package and bootstrap compression)
    - ArchLinux: [pxz-git in the AUR](https://aur.archlinux.org/packages/pxz-git). The pxz package corrupts tarballs fairly frequently.
    - Fedora 23: `sudo dnf install pxz`

## Setup a build environment
Get the code, move into the repository
```
$ git clone https://github.com/dcos/dcos.git
$ cd dcos
```

Write a configuration file for the release tool. We're going to use a local folder $HOME/dcos-artifacts as a repository for all of the DC/OS build artifacts for development / testing. Amazon Web Services S3 and Azure Blob Storage can also both be used. The storage providers are all defined in `release/storage/`. config/dcos-release.config.yaml has the configuration used for the CI that pushes to downloads.dcos.io.
```
$ cat <<EOF > dcos-release.config.yaml
storage:
  local:
    kind: local_path
    path: $HOME/dcos-artifacts
options:
  preferred: local
  cloudformation_s3_url: https://change_me_to_use_the_aws_templates_and_webpages/
EOF
```

## Building and Pushing to the Storage

Setup a python virtual environment, and then use `release` tool to build / release DC/OS and publish it into the storage locations in the configuration file.
```
$ pyvenv ../env
$ source ../env/bin/activate

# Install the release tools, pkgpanda, etc to the virtualenvironment
$ ./prep_local

# NOTE: prep_local doses a "editable" pip install, so most local code changes
# will be visible immediately in `release`, `pkgpanda`, `mkpanda` and the other
# python tools in the repository.

# Create the release release, have it published according to your conifg to the
# channel `testing/first` with a tag `build-demo`
# NOTE: Building a release from scratch the first time on a modern dev machine
# (4 cores / 8 hyper threads, SSD, reasonable interent bandwidth) takes about
# 1 hour.
$ release create first build-demo

# NOTE: release create's first argument is the channel to push two, and the
# second is a tag. The channel could be something like your username, or
#"master". it will make the build appear at
# <storage-path>/testing/<channel-name>/. The tag is an arbitrary identifier to
# denote what the build contains and help track a particular build / feature
# across channels.

# NOTE: Most errors / problems result in Python exceptions + stacktraces. This
# is expected. Usually if you look just above the python exception you'll get a
# more human error message which was the root cause.


# Run the newly built web installer
$ $HOME/dcos-artifacts/testing/first/dcos_generate_config.sh --web
```

## Running python code quality checks
`$ tox`


# TODO

Lots of docs are still being written. If you have immediate questions please ask the [DC/OS Community](https://dcos.io/community/). Someone else probably has exactly the same question.

 - Add getting started on common distros / dependencies
 - Add overview of what is in here, how it works
 - Add general theory of stuff that goes in here.
 - PR (guidelines, testing)
 - How to make different sorts of common changes
