# DC/OS Launch Configuration YAML
## Design Intention
The intention of this configuration file is to provide an interface by which
all deployments of DC/OS, regardless of provider, have a similar format, thus
complementing the goal of dcos-launch to provide a single tool for launching
across a variety of provider APIs.

## Supported Deployments and Examples
- [Simple AWS Cloudformation](aws-cf.yaml)
- [Zen AWS Cloudformation](aws-zen-cf.yaml)
- [AWS Bare (no DC/OS) Cluster](aws-bare-cluster.yaml)
- [Onprem Install on AWS Bare Cluster](aws-onprem.yaml)
- [Onprem Install on Previously Provisioned Linux Cluster](bare-cluster-onprem.yaml)
- [Azure Template Deployment](azure.yaml)

## Keywords and Definitions
### Required Fields
* `launch_config_version`: this is still a tool under active development and as such a strict version specifier must be included
* `platform`: The provider for hardware on which DC/OS will be deployed. May be one of `aws`, `azure`, or `bare_cluster`. See `deploy_bare_cluster_only` and `provider: onprem`
  * `aws`: Requires additional arguments: `deployment_name`, `aws_region`, `aws_access_key_id`, and `aws_secret_access_key`
  * `azure`: Requires additional arguments: `deployment_name`, `azure_location`, `azure_tenant_id`, `azure_subscription_id`, `azure_client_id`, `azure_client_secret`
  * `bare_cluster`: Requires additional argument: `platform_info_filename`. Specifies the info.json file for a previous onprem provider deployment in which `deploy_bare_cluster_only` was set to `true` to allow manipulating the cluster before launch
* `provider`: Which of the DC/OS provisioning methods will be used in this deployment. May be one of `aws`, `azure`, or `onprem`
  * `aws`: Uses Amazon Web Services (AWS) CloudFormation console. Supports both zen and simple templates. (Can only be used with `platform: aws`. Requires: `template_url`, `template_parameters`
  * `azure`: Uses Azure Resource Manager deployment templates. Supports both ACS (Azure Container Service) and DC/OS templates. (Can only be used with `platform: azure`. Requires `template_url`, and `template_parameters`
  * `onprem`: Uses the DC/OS bash installer to orchestrate a deployment on arbitrary hosts of a bare cluster. Requires `num_masters`, `num_private_agents`, `num_public_agents`, `installer_url`, `instance_type`, `os_name`, and `dcos_config`

### Conditionally Required Fields
* `ssh_user`: If `provider: onprem` is used, then the host VM configuration is known to dcos-launch and this value will be calculated. Otherwise, it should always be supplied, and must be supplied for `provider: onprem`
* `ssh_private_key_filename`: If `key_helper` is `true` then this field cannot be supplied. Otherwise it should always be specified, and it is absolutely required for `onprem` deploy
* `instance_count`: If `deploy_bare_cluster_only: true` (see below), then this field must be provided. Note: when this bare cluster is used again with dcos-launch, then the instance count must match `1 + num_master + num_private_agents + num_public_agents`
* `aws_key_name`: If `key_helper: false` and `provider: onprem` and `platform: aws`, then a pre-existing EC2 SSH KeyPair must be supplied for launching the VPC
_Note_: DC/OS deployed from aws or azure provider do not technically need `ssh_user` or `ssh_private_key_filename`. However, without this additional data, the integration tests will not be trigger-able from dcos-launch. Thus, it is not recommended, but allowable, to omit these fields when not using the onprem provider

### Options
* `key_helper`: generate private SSH keys for the underlying hosts if `true`. In `platform: aws`, this means the user does not have to supply `KeyName` in the template parameters and dcos-launch will fill it in. Similarly, in `platform: azure`, `sshRSAPublicKey` is populated automatically. In the aws case, this key will be deleted from EC2 when the deployment is deleted with dcos-launch
* `zen_helper`: only to be used with `provider: aws` and zen templates. If `true`, then the network prerequisites for launching a zen cluster will be provided if missing. As with `key_helper`, these resources will be deleted if dcos-launch is used for destroying the deployment
* `deploy_bare_cluster_only`: only to be used with `provider: onprem`. If `true`, then the onprem deployment will stop after the bare cluster hosts have been provisioned. Like any dcos-launch deployment, this will generate a cluster-info JSON. This JSON can then be passed back into another dcos-launch deployment for `provider: onprem` with `platform: bare_cluster`, by providing the field `platform_info_filename`

### Support
* `onprem` can only be provisioned via `aws` platform (and aws-provided `bare_cluster`)
