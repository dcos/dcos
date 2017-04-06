# DC/OS - The Datacenter Operating System

The easiest way to run microservices, big data, and containers in production.


# What is DC/OS?

Like traditional operating systems, DC/OS is system software that manages computer hardware and software resources and provides common services for computer programs.

Unlike traditional operating systems, DC/OS spans multiple machines within a network, aggregating their resources to maximize utilization by distributed applications.

To learn more, see the [DC/OS Overview](https://dcos.io/docs/latest/overview/).


# How Do I...?

- Learn More - <https://dcos.io/>
- Find the Docs - <https://dcos.io/docs/>
- Install - <https://dcos.io/install/>
- Get Started - <https://dcos.io/get-started/>
- Get Help - <http://chat.dcos.io/>
- Join the Discussion - <https://groups.google.com/a/dcos.io/d/forum/users>
- Report an Issue - <https://dcosjira.atlassian.net>
- Contribute - <https://dcos.io/contribute/>


# Releases

DC/OS releases are publicly available on <http://dcos.io/releases/>

Release artifacts are managed by Mesosphere on Amazon S3, using a CloudFront cache.

To find the git SHA of any given release, check the latest commit in the versioned branches on GitHub: <https://github.com/dcos/dcos/branches/>

| Release Type | URL Pattern |
|--------------|--------------------|
| Latest Stable| `https://downloads.dcos.io/dcos/stable/dcos_generate_config.sh` |
| Specific Stable Release | `https://downloads.dcos.io/dcos/stable/commit/<git-sha>/dcos_generate_config.sh` |
| Latest Early Access | `https://downloads.dcos.io/dcos/EarlyAccess/dcos_generate_config.sh` |
| Specific Early Access Release | `https://downloads.dcos.io/dcos/EarlyAccess/commit/<git-sha>/dcos_generate_config.sh` |
| Latest Master | `https://downloads.dcos.io/dcos/testing/master/dcos_generate_config.sh` |
| Specific PR, Latest Build	| `https://downloads.dcos.io/dcos/testing/pull/<github-pr-number>/dcos_generate_config.sh` |


# Development Environment

**Linux is required for building and testing DC/OS.**

1. Linux distribution:
  - Docker doesn't have all the features needed on OS X or Windows
  - `tar` needs to be GNU tar for the set of flags used
1. [tox](https://tox.readthedocs.org/en/latest/)
1. git 1.8.5+
1. Docker 1.11
  - [Install Instructions for various distributions](https://docs.docker.com/engine/installation/). Docker needs to be configured so your user can run docker containers. The command `docker run alpine  /bin/echo 'Hello, World!'` when run at a new terminal as your user should just print `"Hello, World!"`. If it says something like "Unable to find image 'alpine:latest' locally" then re-run and the message should go away.
1. Python 3.5
  - Arch Linux: `sudo pacman -S python`
  - Fedora 23 Workstation: Already installed by default / no steps
  - Ubuntu 16.04 LTS:
    - [pyenv-installer](https://github.com/yyuu/pyenv-installer)
    - Python dependencies: `sudo apt-get install make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev xz-utils liblzma-dev`
    - Install Python 3.5.2: `pyenv install 3.5.2`
    - Create DC/OS virtualenv: `pyenv virtualenv 3.5.2 dcos`
    - Activate environment: `pyenv activate dcos`
1. Over 10GB of free disk space
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
    source /opt/mesosphere/environment.export
    python /opt/mesosphere/active/dcos-oauth/bin/dcos_add_user.py albert@bekstil.net
    ```

    This test user has a known login token with far future expiration. DO NOT USE IN PRODUCTION!

    After the test, remember to delete the test user.
    For more information, see [User Management](https://dcos.io/docs/latest/administration/user-management/).

1. Configure the tests

    ```
    source /opt/mesosphere/active/dcos-integration-test/test_env.export
    export SLAVE_HOSTS=<PRIVATE-AGENT-IP-1>,<PRIVATE-AGENT-IP-2>
    export PUBLIC_SLAVE_HOSTS=<PUBLIC-AGENT-IP-1>,<PUBLIC-AGENT-IP-2>
    ```

    The `test_env.export` script tries to look up cluster metadata, but can't distinguish between public and private nodes yet. So those have to be manually specified.

1. Run the tests with Pytest

    ```
    cd /opt/mesosphere/active/dcos-integration-test
    py.test
    ```

## Using DC/OS Docker

One way to run the integration tests is to use [DC/OS Docker](https://github.com/dcos/dcos-docker).

1. Setup DC/OS in containers using [DC/OS Docker](https://github.com/dcos/dcos-docker).

1. `exec` into the master node

	```
	docker exec -it dcos-docker-master1 /bin/bash
	```

1. Configure the tests

    ```
	export DCOS_DNS_ADDRESS=http://172.17.0.2
	export MASTER_HOSTS=172.17.0.2
	export PUBLIC_MASTER_HOSTS=172.17.0.2
	export SLAVE_HOSTS=172.17.0.3
	export PUBLIC_SLAVE_HOSTS=172.17.0.4
	export DCOS_PROVIDER=onprem
	export DNS_SEARCH=false
	export DCOS_LOGIN_PW=admin
	export PYTHONUNBUFFERED=true
	export PYTHONDONTWRITEBYTECODE=true
	export DCOS_LOGIN_UNAME=admin
	export TEST_DCOS_RESILIENCY=false
	source /opt/mesosphere/environment.export
    ```

1. Run the tests with Pytest

    ```
    cd /opt/mesosphere/active/dcos-integration-test
    py.test
    ```

# Build

DC/OS can be built locally but requires the [development environment](#development-environment) specified above.

DC/OS builds are packaged as a self-extracting Docker image wrapped in a bash script called `dcos_generate_config.sh`.

**WARNING**: Building a release from scratch the first time on a modern dev machine (4 cores / 8 hyper threads, SSD, reasonable internet bandwidth) takes about 1 hour.

## Instructions

```
./build_local.sh
```

That will run a simple local build, and output the resulting DC/OS installers to $HOME/dcos-artifacts. You can run the created `dcos_generate_config.sh like so:

```
$ $HOME/dcos-artifacts/testing/`whoami`/dcos_generate_config.sh
```

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

Sample config that will store to a local archive path as wll as AWS S3. Environment variables AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY would need to be set to use the config (And something like a CI system could provide them so they don't have to be committed to a code repository).
```yaml
storage:
  aws:
    kind: aws_s3
    bucket: downloads.dcos.io
    object_prefix: dcos
    download_url: https://downloads.dcos.io/dcos/
    access_key_id: $AWS_ACCESS_KEY_ID
    secret_access_key: $AWS_SECRET_ACCESS_KEY
    region_name: us-west-2
  local:
    kind: local_path
    path: /mnt/big_artifact_store/dcos/
```


# Pull Requests

Pull requests automatically trigger a new build and several tests.

Most of the triggered tests are required for merge, but some are optional (usually ones on flaky infrastructure).

- teamcity/create-release-pr: in [the CI system](https://teamcity.mesosphere.io/project.html?projectId=DcosIo_Dcos&tab=projectOverview), [build_teamcity](https://github.com/dcos/dcos/blob/master/build_teamcity) is triggered and developers should use [build_local.sh](https://github.com/dcos/dcos/blob/master/build_local.sh) (see above)
- teamcity/code-quality: simply run `tox` in the top-level dir to run all syntax checks as well as pytest (unit-tests). See [tox.ini](https://github.com/dcos/dcos/blob/master/tox.ini) for more details
- integration-test/*: runs [integration_test.py](https://github.com/dcos/dcos/blob/master/test_util/integration_test.py) in the network of a DC/OS cluster
    - /vagrant-bash: Tests the on-prem bash provider by using [dcos-vagrant](https://github.com/dcos/dcos-vagrant). Invoke this test through [run-all](https://github.com/dcos/dcos/blob/master/test_util/run-all)
    - /deploy-vpc-cli: runs [ccm-deploy-test](https://github.com/dcos/dcos/blob/master/test_util/test_installer_ccm.py) with USE_INSTALLER_API=false. A Virtual Private Cloud of CentOS nodes is spun up by CCM (Mesosphere's Cloud Cluster Manager) and the installer (dcos_generate_config.sh) is used via the CLI options to deploy DC/OS. Finally, the same integration_test.py is run
    - /deploy-vpc-api: the same as /deploy-vpc-cli (see above) except uses USE_INSTALLER_API=true, which causes the installer to be started with the `--web` option and then controlled entirely by the HTTP API


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
