# DC/OS - The Datacenter Operating System

The easiest way to run microservices, big data, and containers in production.


# What is DC/OS?

Like traditional operating systems, DC/OS is system software that manages computer hardware and software resources and provides common services for computer programs.

Unlike traditional operating systems, DC/OS spans multiple machines within a network, aggregating their resources to maximize utilization by distributed applications.

To learn more, see the [DC/OS Overview](https://docs.d2iq.com/mesosphere/dcos/latest/overview/).


# How Do I...?

- Learn More - <https://dcos.io/>
- Find the Docs - <https://dcos.io/docs/>
- Install - <https://dcos.io/install/>
- Get Started - <https://dcos.io/get-started/>
- Get Help - <http://chat.dcos.io/>
- Join the Discussion - <https://groups.google.com/a/dcos.io/d/forum/users>
- Report an Issue - <https://jira.dcos.io>
- Contribute - <https://dcos.io/contribute/>


# Releases

DC/OS releases are publicly available on <http://dcos.io/releases/>

Release artifacts are managed by Mesosphere on Amazon S3, using a CloudFront cache.

To find the git SHA of any given release, check the latest commit in the versioned branches on GitHub: <https://github.com/dcos/dcos/branches/>

| Release Type | URL Pattern |
|--------------|--------------------|
| Latest Stable| `https://downloads.dcos.io/dcos/stable/dcos_generate_config.sh` |
| Latest Master| `https://downloads.dcos.io/dcos/testing/master/dcos_generate_config.sh` |
| Latest Build of Specific PR| `https://downloads.dcos.io/dcos/testing/pull/<github-pr-number>/dcos_generate_config.sh` |


# Development Environment

**Linux is required for building and testing DC/OS.**

1. Linux distribution:
    - Docker doesn't have all the features needed on OS X or Windows
    - `tar` needs to be GNU tar for the set of flags used
    - `unzip` needs to be installed
1. [pre-commit](https://pre-commit.com)
1. [tox](https://tox.readthedocs.org/en/latest/)
1. git 1.8.5+
1. Docker 1.11+
    - [Install Instructions for various distributions](https://docs.docker.com/engine/installation/). Docker needs to be configured so your user can run docker containers. The command `docker run alpine  /bin/echo 'Hello, World!'` when run at a new terminal as your user should just print `"Hello, World!"`. If it says something like "Unable to find image 'alpine:latest' locally" then re-run and the message should go away.
1. Python 3.6
    - Arch Linux: `sudo pacman -S python`
    - Fedora 23 Workstation: Already installed by default / no steps
    - Ubuntu 16.04 LTS:
        - [pyenv-installer](https://github.com/yyuu/pyenv-installer)
        - Python dependencies: `sudo apt-get install make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev xz-utils liblzma-dev python3-venv`
        - Install Python 3.6.3: `pyenv install 3.6.3`
        - Create DC/OS virtualenv: `pyenv virtualenv 3.6.3 dcos`
        - Activate environment: `pyenv activate dcos`
1. Over 10GB of free disk space and 8GB of RAM
    - The build makes use of hard links, so if you're using VirtualBox the disk space cannot be a synced folder.
1. _Optional_ pxz (speeds up package and bootstrap compression)
    - ArchLinux: [pxz-git in the AUR](https://aur.archlinux.org/packages/pxz-git). The pxz package corrupts tarballs fairly frequently.
    - Fedora 23: `sudo dnf install pxz`

# Unit Tests

Unit tests can be run locally but require the [development environment](#development-environment) specified above.

```
tox
```

[Tox](https://tox.readthedocs.io/en/latest/) is used to run the codebase unit tests, as well as coding standard checks. The config is in `tox.ini`.


# Integration Tests

Integration tests can be run on any deployed DC/OS cluster. For installation instructions, see <https://dcos.io/install/>.

Integration tests are installed via the [dcos-integration-test](./packages/dcos-integration-test/) Pkgpanda package.

Integration test files are stored on the DC/OS master node at `/opt/mesosphere/active/dcos-integration-test`.
Therefore, in order to test changes to test files, move files from `packages/dcos-integration-test/extra/` in your checkout to `/opt/mesosphere/active/dcos-integration-test` on the master node.

The canonical source of the test suite's results is the continuous integration system.
There may be differences between the results of running the integration tests as described in this document and the results given by the continuous integration system.
In particular, some tests may pass on the continuous integration system and fail locally or vice versa.

## Minimum Requirements

- 1 master node
- 2 private agent nodes
- 1 public agent node
- Task resource allocation is currently insignificantly small
- DC/OS itself requires at least 2 (virtual) cpu cores on each node

## Instructions

1. SSH into a master node
The tests can be run via Pytest while SSH'd as root into a master node of the cluster to be tested.

1. Switch to root

    ```
    sudo su -
    ```

1. Add the test user

    ```
    dcos-shell python /opt/mesosphere/bin/dcos_add_user.py albert@bekstil.net
    ```

    Running the above mentioned command will result in an output

    ```
    User albert@bekstil.net successfully added
    ```

    This test user has a known login token with far future expiration. DO NOT USE IN PRODUCTION.
    After the test, remember to delete the test user.

    For more information, see [User Management](https://docs.mesosphere.com/latest/security/oss/user-management/).


2. Run the tests using pytest in the cluster.

    ```
    cd /opt/mesosphere/active/dcos-integration-test
    dcos-shell pytest
    ```

## Using a Docker Cluster with miniDC/OS

One way to run the integration tests is to use the [miniDC/OS CLI](https://minidcos.readthedocs.io/en/latest/).

This lets you create, run and manage clusters in test environments.
Each DC/OS node is represented by a Docker container.

1. Setup DC/OS in containers using the [miniDC/OS CLI](http://minidcos.readthedocs.io/en/latest/).

For example, after [installing the miniDC/OS CLI](http://minidcos.readthedocs.io/en/latest/#installation), create a cluster:

```
minidcos docker download-installer
minidcos docker create /tmp/dcos_generate_config.sh \
    --masters 1 \
    --agents 2 \
    --public-agents 1 \
    --cluster-id default
```

2. Run `minidcos docker wait`

Wait for DC/OS to start.
Running wait command allows to make sure that the cluster is set up properly before any other actions that could otherwise cause errors in `pytest` command in the next step.

3. Run `pytest` on a master node.

For example:

```
minidcos docker run --test-env pytest
```

4. Destroy the cluster.

```
minidcos docker destroy
```

# Build

DC/OS can be built locally but requires the [development environment](#development-environment) specified above.

DC/OS builds are packaged as a self-extracting Docker image wrapped in a bash script called `dcos_generate_config.sh`.

**WARNING**: Building a release from scratch the first time on a modern dev machine (4 cores / 8 hyper threads, SSD, reasonable internet bandwidth) takes about 1 hour.

## Instructions

```
./build_local.sh
```

That will run a simple local build, and output the resulting DC/OS installers to `./packages/cache/dcos_generate_config.sh`:

```
$ ./packages/cache/dcos_generate_config.sh
```

See the section on [running in Docker](#using-a-docker-cluster-with-minidcos) to test the installer.

## Build Details

If you look inside of the bash script `build_local.sh` there are the commands with descriptions of each.

The general flow is to:
 1. Check the environment is reasonable
 2. Write a `release` tool configuration if one doesn't exist
 3. Setup a python virtualenv where we can install the DC/OS python tools to in order to run them
 4. Install the DC/OS python tools to the virtualenv
 5. Build the release using the `release` tool

These steps can all be done by hand and customized / tweaked like standard python projects. You can hand create a virtualenvironment, and then do an editable pip install (`pip install -e`) to have a "live" working environment (as you change code you can run the tool and see the results).

## Release Tool Configuration

This release tool always loads the config in `dcos-release.config.yaml` in the current directory.

The config is [YAML](http://yaml.org/). Inside it has two main sections. `storage` which contains a dictionary of different storage providers which the built artifacts should be sent to, and `options` which sets general DC/OS build configuration options.

Config values can either be specified directly, or you may use $ prefixed environment variables (the env variable must set the whole value).

### Storage Providers

All the available storage providers are in [release/storage](./release/storage/). The configuration is a dictionary of a reference name for the storage provider (local, aws, my_azure), to the configuration.

Each storage provider (ex: aws.py) is an available kind prefix. The dictionary `factories` defines the suffix for a particular kind. For instance `kind: aws_s3` would map to the S3StorageProvider.

The configuration options for a storage provider are the storage provider's constructor parameters.

Sample config storage that will save to my home directory (/home/cmaloney):
```yaml
storage:
  local:
    kind: local_path
    path: /home/cmaloney/dcos-artifacts
```

Sample config that will store to a local archive path as well as AWS S3. To authenticate with AWS S3, reference the [boto3 docs](http://boto3.readthedocs.io/en/latest/guide/configuration.html#configuring-credentials) to learn how to configure access.
```yaml
storage:
  aws:
    kind: aws_s3
    bucket: downloads.dcos.io
    object_prefix: dcos
    download_url: https://downloads.dcos.io/dcos/
  local:
    kind: local_path
    path: /mnt/big_artifact_store/dcos/
```

# Repo Structure

DC/OS itself is composed of many individual components precisely configured to work together in concert.

This repo contains the release and package building tools necessary to produce installers for various on-premises and cloud platforms.

| Directory | Contents |
| --------- | -------- |
| *cloud_images*       | Base OS image building tools
| *config*             | Release configuration
| *docs*               | Documentation
| *flake8_dcos_lint*   | Flake8 plugin for testing code quality
| *dcos_installer*     | Backend for Web, SSH, and some bits of the Advanced installer. Code is being cleaned up
| *gen*                | Python library for rendering yaml config files for various platforms into packages, with utilities to do things like make "late binding" config set by CloudFormation
| *packages*           | Packages which make up DC/OS (Mesos, Marathon, AdminRouter, etc). These packages are built by pkgpanda, and combined into a "bootstrap" tarball for deployment.
| *pkgpanda*           | DC/OS baseline/host package management system. Tools for building, deploying, upgrading, and bundling packages together which live on the root filesystem of a machine / underneath Mesos.
| *release*            | Release tools for DC/OS. (Building releases, building installers for releases, promoting between channels)
| *ssh*                | AsyncIO based parallel ssh library used by the installer
| *test_util*          | various scripts, utilities to help with integration testing


# Pull Requests Statuses

Pull requests automatically trigger a new DC/OS build and run several tests. These are the details on the various status checks against a DC/OS Pull Request.

| Status Check                                   | Purpose                                                                                                                 | Source and Dependencies                                                                                |
|------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| continuous-integration/jenkins/pr-head         | Admin Router Endpoint tests                                                                                             | [dcos/dcos/packages/adminrouter/extra/src/test-harness](https://github.com/dcos/dcos/tree/master/packages/adminrouter/extra/src/test-harness) Docker Dependency: [dcos/dcos/packages/adminrouter](https://github.com/dcos/dcos/blob/master/packages/adminrouter/buildinfo.json) |
| mergebot/enterprise/build-status/aggregate     | EE Test Enforcement                                                                                                     | Private [mesosphere/dcos-enterprise](https://github.com/mesosphere/dcos-enterprise) repo is tested against the SHA.|
| mergebot/enterprise/has_ship-it                | Code Review Enforcement                                                                                                 | Private [Mergebot](https://github.com/mesosphere/mergebot) service in prod cluster                     |
| mergebot/enterprise/review/approved/min_2      | Code Review Enforcement                                                                                                 | Mergebot service in prod cluster                                                                       |
| mergebot/has_ship-it                           | Code Review Enforcement                                                                                                 | Mergebot service in prod cluster                                                                       |
| mergebot/review/approved/min_2                 | Code Review Enforcement                                                                                                 | Mergebot service in prod cluster                                                                       |
| teamcity/dcos/build/dcos                       | Builds DCOS Image (dcos_generate_config.sh)                                                                             | [gen/build_deploy/bash.py](https://github.com/dcos/dcos/blob/master/gen/build_deploy/bash.py)          |
| teamcity/dcos/build/tox                        | Runs check-style, unit-tests                                                                                            | [tox.ini](https://github.com/dcos/dcos/blob/master/tox.ini)                                            |
| teamcity/dcos/test/aws/cloudformation/simple   | Deployment using single-master-cloudformation.json and runs integration tests                                           | [gen/build_deploy/aws.py](https://github.com/dcos/dcos/blob/master/gen/build_deploy/aws.py),           |
| teamcity/dcos/test/terraform/aws/onprem/static/group{1..n}  | Installation via dcos_generation_config.sh and runs Integration Tests                                                | [gen/build_deploy/bash.py](https://github.com/dcos/dcos/blob/master/gen/build_deploy/bash.py), |
| teamcity/dcos/test/test-e2e/group{1..n}        | End to End Tests. Each Test launches a cluster, exercises a functionality.                                              | [test-e2e](https://github.com/dcos/dcos/tree/master/test-e2e)

### Required vs Non-Required Status checks

A PR status check may be marked as **Required** or **Not-Required** (Default). The required status checks are necessary for applying a ship-it label, which makes the PR eligible for merge.
A non-required status check is completely informational, and the success or the failure of the status check does not, in any way, impact the merge of the PR.

The required status checks are encoded in the repo's megebot-config (For .e.g: https://github.com/dcos/dcos/blob/master/mergebot-config.json#L38)
and are enforced by mergebot.
