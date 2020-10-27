# Qualification and Upgrade testing
This test is meant for OS qualification ( OS + Docker ) and upgrade testing.

## Universal Installer
Base for these tests is Universal installer. With `.tfvars` files

## Upgrade testing
Upgrade testing is done by specifying a base version and a target build:

```
DCOS_UPGRADE_BASE=2.1.0 \
  DCOS_UPGRADE_TARGET_URL="<buildurl>" \
  DCOS_UPGRADE_TARGET_VERSION="<build version specifier>" \
  make upgrade
```

## OS Qualification
OS Qualification testing expects a given OS + Docker version.

OS Images are specified as AWS AMI Ids in a dictionary and docker can be specified
as an additional ansible config

like `scenarios/osqualification/centos/7.8.docker-18.09.9.tfvars`
```
os_images = {
  "us-east-1" : "ami-06cf02a98a61f9f5e"
  "us-west-2" : "ami-0a248ce88bcc7bd23"
}

ansible_additional_config = "
dcos_docker_pkgs:
  - docker-ce-18.09.2
  - docker-ce-cli-18.09.2
"
```

n
```
TF_VAR_custom_dcos_download_path="<dcos build to qualify>" \
  TF_VAR_dcos_version="<dcos version to qualify>" \
  SINGLE_QUALIFY_SCENARIO=centos/7.8.docker-18.09.9.tfvars \
  make qualify
```
