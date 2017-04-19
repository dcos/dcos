# `dcos-launch` User Guide
## Overview

`dcos-launch` is a portable linux executable to create, wait for provisioning, describe, test/validate, and destroy an arbitrary cluster. `dcos-launch` can be used as an installed library for development, but it is also shipped as an executable with every DC/OS build. E.g. to get the current `testing/master` version of DC/OS, use this url:
`https://downloads.dcos.io/dcos/testing/master/dcos-launch`

## Features
`dcos-launch` provides the following:
* Consistent interface: launching on Azure or AWS can involve finding a suitable client API and then sifting through hundreds of specific API calls to find the combination that will allow deploying DC/OS. `dcos-launch` has the exact methods required to take a DC/OS build artifact and deploy it to an arbitrary provider with no other tools.
* Turn-key deployment: The only input required by `dcos-launch` is the [launch config](launch/sample_configs/README.md). In cases where artifacts are required to deploy DC/OS (e.g. SSH keys), `dcos-launch` provids helpers to automatically create and cleanup those extra artifacts
* Portable shipping: `dcos-launch` is shipped as a frozen python binary so that you never need to be concerned with maintaining an extremely specific development environment or deployment framework.
* Build verification: besides launching clusters, `dcos-launch` can test that the provisioned cluster is healthy through the `pytest` subcommand. `dcos-launch` is capable of describing the cluster topology and verifying that the expected cluster is present. To learn more about the testing suite triggered by this command, see: [dcos-integration-test](../../dcos-integration-test/extra)
* Programmatic consumption: all information necessary to interact with a given deployment configuration created by `dcos-launch` is contained in the generated `cluster_info.json` file. This allows dependent CI tasks to run other tests, describe the cluster, or completely delete the cluster

## Requirements
* Linux operating system
* SSH client installed on localhost

## Commands
### `dcos-launch create`
Consumes a [launch config file](launch/sample_configs/README.md) file, performs basic validation on the deployment parameters, and then signals the deployment provider to begin deployment. By default, `dcos-launch` will expect a launch config at `config.yaml` but any arbitrary path can be passed with the `-c` option. If creation is triggered successfully, then a `cluster_info.json` file will be produced for use with other `dcos-launch` commands. This path is also configurable via the `-i` command line option

In the case of third-party provisioning (provider is AWS or Azure), the cluster will eventually finish deploying with no further action. In the case of onprem provisioning, `dcos-launch` needs to partially drive the deployment process, so the `dcos-launch create` command only triggers creation of the underlying bare hosts, while `dcos-launch wait` will step through the DC/OS installer stages.

### `dcos-launch wait`
Reads the cluster info from the create command to see if the deployment is ready and blocks if the cluster is not ready. In the case of third-party providers, this command will query their deployment service and surface any errors that may have derailied the deployment. In the case of onprem provisioning, there are multiple, triggerable stages in deployment, so the wait command *must* be used to complete the deployment.

### `dcos-launch describe`
Reads the cluster info and outputs the essential parameters of the cluster. E.g. master IPs, agent IPs, load balancer addresses. Additionally, the STDOUT stream is formatted in JSON so that the output can be piped into another process or tools like `jq` can be used to pull out specific paramters.

### `dcos-launch pytest`
Reads the cluster info and runs the [dcos-integration-test](../../dcos-integration-test/extra) package. This is the same test suite used to validate DC/OS pull requests. Additionally, arbitrary arguments and environment variables may be added to the pytest command. For example, if one only wants to run the cluster composition test to see if the cluster is up: `dcos-launch pytest -- test_composition.py`. Anything input after `--` will be injected after `pytest` (which is naturally run without options).

### `dcos-launch delete`
Reads the cluster info and triggers the destruction of the deployment. In cases where `dcos-launch` provided third-party dependencies via a helper (`zen_helper` or `key_helper` for AWS), `delete` will block until all those resources have been removed.

## Options
### `-c PATH`
By default, `dcos-launch` assumes `config.yaml` in your working directory to be the config file path, but this option allows specifying a specific file. Note: this option is only used for `create`. E.g. `dcos-launch create -c aws_cf_config.yaml`

### `-i PATH`
By default, the info path is set as `cluster_info.json`, but this option allows overriding. Thus, a user may have multiple configurations and cluster infos simultaneously. Note: in the case of create, this option indicates where the JSON will be created whereas for the other commands it indicated where the JSON is read from. E.g. `dcos-launch delete -i onprem_cluster_info.json`

### `-L LEVEL`
By default, the log level is info. By using this option you will also be able to control the test logging level in addition to the provisioning/launch logging level. Choices are: debug, info, warning, error, exception. E.g. `dcos-launch wait -L debug`

### `-e LIST`
This option allows passing through environment variables from the current environment into the testing environment. The list is comma delimited and any provided environment variables will override the automatically injected ones. Required variables that are automatically injected include `MASTER_HOSTS`, `SLAVE_HOSTS`, `PUBLIC_MASTER_HOSTS`, `PUBLIC_SLAVE_HOSTS`, `DCOS_DNS_ADDRESS`. E.g. `dcos-launch pytest -e MASTER_HOSTS -- test_composition.py`, `ENABLE_RESILIENCY_TESTS=true dcos-launch pytest -e ENABLE_RESILIENCY_TESTS,MASTER_HOSTS -- test_applications.py`
