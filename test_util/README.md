# DC/OS Testing

The dcos-integration-test harness and cloud deployment utilities that were previously hosted in this directory have been
moved to: [DC/OS Test Utils](https://github.com/mesosphere/dcos-test-utils)

Currently, this directory contains terraform helpers.

## Running a Cluster and all Tests

The cluser creation and tests are orchestrated with a [Makefile](Makefile). Given you have an active AWS session, eg.
via [maws](https://github.com/mesosphere/maws), you can trigger all tests with

```
DCOS_LICENSE_CONTENTS=$(cat ~/license.txt) make test
```

### Targets

`cluster.json` launches a cluster and writes all Terraform outputs such as the IP addresses of nodes into a JSON file.
The file is used to run the tests.

`destroy` destroys a cluster.

`ssh` will SSH into the master of the cluster.

`test` launches a cluster if no `cluster.json` is found and runs all tests.

### Options

`AWS_REGION` defines the AWS region used for the cluster. It defaults to `us-west-2`.

`DCOS_LICENSE_CONTENTS` must be the contents of a DC/OS license.

`TERRAFORM` defines the path to the Terraform executable. If this variable is not set `make` will download the binary to
the local folder.

`SSH_KEY` can be set to your local private SSH key file. If no key exists it creates it. Defaults to
`./tf-dcos-rsa.pem`.

`TF_VAR_custom_dcos_download_path` defines the download for `dcos_generate_config.sh`. It defaults to the master
version. It can be used to test pull request clusters: `TF_VAR_custom_dcos_download_path=https://downloads.dcos.io/dcos/testing/pull/6956/dcos_generate_config.sh`.

`TF_VAR_custom_dcos_download_path_win` define the download for `dcos_generate_config_win.sh`. It defaults to the master
version. It can be used to test pull request clusters: `TF_VAR_custom_dcos_download_path_win=https://downloads.dcos.io/dcos/testing/pull/6956/windows/dcos_generate_config_win.sh`.

`TF_VAR_variant` determines wether the cluster is `open` or `ee`. It defaults to `open`.

`TF_VAR_dcos_security` determines wether the cluster is `permissive`, `strict` (only in enterprise) or empty. It defaults to empty string.

`OVERWRITE_INTEGRATION_TESTS` rsyncs the local integration tests [folder](../packages/dcos-integration-test/extra/) into the cluster and overwrites its packaged default tests.

`PYTEST_EXTRA_ARGS` set pytest args to be executed e.g. `-k 'not ..'`

### Under the Hood

We use Terraform to launch cluster. The `main.tf` describes the creation.  You can change the configuration of the cluster.
All variables are defined at the top of [main.tf](main.tf) and can be set via
[environment variables](https://www.terraform.io/docs/configuration-0-11/variables.html#environment-variables).

Given an active AWS session and a region:

```
$(maws li "eng-mesosphere-marathon")
export AWS_REGION="us-east-1"
```

you can start a cluster with

```
terraform init --upgrade
terraform apply
```

Once Terraform finished you can setup the CLI with `dcos cluster setup $(terraform output dcos_ui) --insecure`.

Do not forget to destroy the cluster again with `terraform destroy`.

By default instances will be destroyed by CloudCleaner to change expiration set `TF_VAR_expiration=8h` and `TF_VAR_owner=$USER`.

### Makefile includes for other test environments
This repository can be used as an library for other tests. Like the lokal [Makefile](./Makefile) following lines can be used to include the different targets:

```Makefile
# Terraform binary management
include terraform.mk
# Universal Installer related targets
include dcos.mk
# DC/OS diagnostics handling
include diagnostics.mk
```

The simplest way of using these shared targets is a direct mapping:

```Makefile
.PHONY: test
test: dcos-test

.PHONY: destroy
destroy: dcos-destroy

.PHONY: clean
clean: dcos-clean
```

But also more completx scenarios are possible. Have a look into [test-upgrade](../test-upgrade) [test-qualification](../test-qualification)
