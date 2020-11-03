# Upgrade testing [WIP]
Upgrade testing deploys a cluster in a given version `DCOS_UPGRADE_BASE_VERSION` and runs an upgrade to `DCOS_UPGRADE_TARGET_VERSION` also URLS could be specified.

Currently testing is not yet implemented. the Targets `upgrade-base-pretest.json` and `upgrade-target-test` are meant for pre and post upgrade procedures making sure tasks survive an upgrade.

## Variables

- `DCOS_UPGRADE_BASE_VERSION` - The version to start with.
- `DCOS_UPGRADE_BASE_URL` (Optional) - Download URL to be used with the given version
- `DCOS_UPGRADE_TARGET_VERSION` - The version to upgrade to.
- `DCOS_UPGRADE_TARGET_URL` (Optional) - Download URL to be used as the target version

Other available variables could be found in [test_util](../test_util)


## Targets and order
The following targets and order are automatically executed with `make test`


1. `%.tf` - copy *.tf from [test_util](../test_util)
2. `terraform.tfvars` - create a tfvars file with the base parameters like version or url
3. `cluster.json` - start the DC/OS deployment
4. `upgrade-base-pretest.json` - execute pre tests before starting the upgrade
5. `upgrade.auto.tfvars` - Create an auto.tfvars file overwriting the base settings with target version and url
6. `cluster-upgrade.json` - Execute upgrade on the cluster
7. `upgrade-target-test` - Execute post upgrade testing

## Other targets
- `destroy` destroys the cluster
- `clean` cleans up the local folder
