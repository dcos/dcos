<<<<<<< HEAD
variable "AWS_REGION" {}
variable "teamcity_build_id" {}
variable "ONPREM_INSTALLER_URL" {}
variable "ONPREM_AWS_INSTANCE_SIZE" {}
variable "system_teamcity_buildType_id" {}
=======
variable "AWS_REGION" {
  type = "string"
  default = "us-west-2"
}

variable "custom_dcos_download_path" {
  type = "string"
  default = "https://downloads.dcos.io/dcos/testing/master/dcos_generate_config.sh"
}

variable "variant" {
  type = "string"
  default = "strict"
}

variable "dcos_security" {
  type = "string"
  default = ""
}

variable "owner" {
    type = "string"
    default = "dcos/test_util"
}

variable "expiration" {
    type = "string"
    default = "3h"
}

variable "ssh_public_key_file" {
  type = "string"
  default = "id_rsa.pub"
  description = "Defines the public key to log on the cluster."
}

variable "dcos_license_key_contents" {
  type = "string"
  default = ""
  description = "Defines content of license used for EE."
}

variable "instance_type" {
    type = "string"
    default = "t3.medium"
    description = "Defines type of used machine."
}

variable "build_id" {
    type = "string"
    default = ""
    description = "Build ID from CI."
}

variable "build_type" {
    type = "string"
    default = ""
    description = "Build type from CI."
}

variable "password_hash" {
  type = "string"
  default = ""
}
>>>>>>> c116e36... Update main.tf removing EE references

provider "aws" {
  region = "${var.AWS_REGION}"
}

# Used to determine your public IP for forwarding rules
data "http" "whatismyip" {
  url = "http://whatismyip.akamai.com/"
}

module "dcos" {
  source  = "dcos-terraform/dcos/aws"
  version = "~> 0.2.10"

  cluster_name        = "tf-ci-${var.teamcity_build_id}-"
  cluster_name_random_string = true
  
  ssh_public_key_file = "id_rsa.pub"
  admin_ips           = ["${data.http.whatismyip.body}/32"]

  num_masters        = "1"
  num_private_agents = "2"
  num_public_agents  = "1"

  custom_dcos_download_path = "${var.ONPREM_INSTALLER_URL}"

  dcos_instance_os    = "centos_7.5"
  bootstrap_instance_type = "${var.ONPREM_AWS_INSTANCE_SIZE}"
  masters_instance_type  = "${var.ONPREM_AWS_INSTANCE_SIZE}"
  private_agents_instance_type = "${var.ONPREM_AWS_INSTANCE_SIZE}"
  public_agents_instance_type = "${var.ONPREM_AWS_INSTANCE_SIZE}"
  #AVAILABILITYZONES

  dcos_calico_network_cidr = "172.17.0.0/16"
  dcos_variant = "open"

  providers = {
    aws = "aws"
  }

  tags = {
    build_id = "${var.teamcity_build_id}"
    build_type_id = "${var.system_teamcity_buildType_id}"
  }
}

output "masters-ips" {
  value = "${module.dcos.masters-ips}"
}

output "cluster-address" {
  value = "${module.dcos.masters-loadbalancer}"
}

output "public-agents-loadbalancer" {
  value = "${module.dcos.public-agents-loadbalancer}"
}
