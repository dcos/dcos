# DC/OS Testing

The dcos-integration-test harness and cloud deployment utilities that were previously hosted in this directory have been moved to: [DC/OS Test Utils](https://github.com/mesosphere/dcos-test-utils)

Currently, this directory contains terraform helpers.

## Lauching a Cluster

You must have an active AWS CLI session. The easiest way is to use [maws](https://github.com/mesosphere/maws).

```
$(maws li "eng-mesosphere-marathon")
export AWS_REGION="us-east-1"
```

The private SSH key for the public key defined in `main.tf` must be added with `ssh-add ~/.ssh/id_rsa`.

Terraform 0.11 must also be on your machine. Then call

```
terraform init --upgrade
terraform apply
```

to start a cluster.

Once Terraform finished you can setup the CLI with `dcos cluster setup $(terraform output masters_dns_name) --insecure`.

Do not forget to destroy the cluster again with `terraform destroy`.

### Configuration

You can change the configuration of the cluster. All variables are defined at the top of [main.tf](main.tf) and can be
set via [environment variables](https://www.terraform.io/docs/configuration-0-11/variables.html#environment-variables).

```
export TF_VAR_custom_dcos_download_path="https://downloads.dcos.io/dcos/testing/master/dcos_generate_config.sh"
export TF_VAR_custom_dcos_download_path_win="https://downloads.dcos.io/dcos/testing/master/windows/dcos_generate_config_win.sh"
export TF_VAT_variant="open"
terraform init --upgrade
terraform apply
```

If you want to launch the build of a specific pull request simply replace `master` with `pull/<PR#>`. The number of
Windows agents defaults to zero and can be set via `TF_VAR_windowsagent_num`.
