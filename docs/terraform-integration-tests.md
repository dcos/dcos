DC/OS is tested in TeamCity by several groups of integration tests using dcos-terraform and AWS spot instances.

# Connecting to a test cluster

Once the TeamCity job has completed, the DC/OS cluster that was created will be deleted. However, if the job is still running, you can connect to the cluster.

Once `terraform apply` has completed, the job outputs to the job log the generated SSH key, cluster address, and node IP addresses as well as a bash one liner to write the SSH key to disk and SSH into the master node.

# Creating a Terraform cluster

To create a cluster with Terraform, see the [official Universal Installer documentation](https://docs.mesosphere.com/1.12/installing/evaluation/aws/).

# Get the helper scripts

The DC/OS repository has a couple of helper scripts to help setup the Terraform module to use spot instances, collect logs from a cluster, and run integration tests against a cluster.

The scripts live in the master branch of the `dcos/dcos` repository. Clone it, if you haven't:

```
git clone https://github.com/dcos/dcos.git /tmp/dcos
```

# Reproducing issues locally

Every TeamCity integration test job includes the `main.tf` file used to create the cluster in its build log (at runtime) and in the artifacts (after the build has completed).

To recreate a cluster from a TeamCity job:

1. Clone the DC/OS repository: `git clone https://github.com/dcos/dcos.git /tmp/dcos`.
2. Create a new directory.
3. Download the `main.tf` file to the new directory.
4. Login to AWS: `eval $(maws login "account name")`.
5. Start your SSH agent: `eval $(ssh-agent)`.
6. Run `/tmp/dcos/test_util/terraform_init.sh`.
7. Optionally, run the tests: `/tmp/dcos/test_util/terraform_test.sh $test_group_number`.
8. Optionally, download the logs: `/tmp/dcos/test_util/terraform_logs.sh` or `/tmp/dcos/test_util/terraform_logs.sh enterprise` for an enterprise cluster.

# Running tests

The `./test_util/terraform_test.sh` script runs the DC/OS integration tests against the created DC/OS cluster.

The tests are run in four groups, specify the group to run as the first argument:

```
/tmp/dcos/test_util/terraform_tesh.sh 1
```

# Collecting logs

The `./test_util/terraform_logs.sh` script collects logs and diagnostics from the cluster into a local `logs/` directory.

If the cluster is an OSS cluster:

```
/tmp/dcos/test_util/terraform_logs.sh open
```

If it is enterprise:

```
/tmp/dcos/test_util/terraform_logs.sh enterprise
```
