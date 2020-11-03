# Qualification testing
Qualifitacation testing is used to execute different OSes, packages or setups with Universal Installer and verify them by executing integration-tests.

## Create a scenario file.
The scenarios folder structure is expected to be `<OS>/<scenario>`. The example is executing a default deployment on `centos-7.8.2003`.

### `scenarios/centos-7.8.2003/terraform.tfvars`
Depending on the selected scnario Makefile is copying `terraform.tfvars` to the execution folder and therefore automatically applying its variables.

The given scenario uses `aws_region_amis` to set an AMI for masters and angents depending on the current region. Scenarios could include every variable available in [variables.tf](../test_util/variables.tf)

```
aws_region_amis = {
  "us-east-1" : "ami-06cf02a98a61f9f5e"
  "us-west-2" : "ami-0a248ce88bcc7bd23"
}
```

## Running a test
To run a given scenario we use `make`

```bash
SCENARIO=centos-7.8.2003/defaults make test
```

This executes a deplyoment using the variables from the scenario and execute the integration tests afterwards.

## Variables
Check the test_util [README.md](../test_util/README.md) for more information
