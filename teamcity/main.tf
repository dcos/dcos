variable "AWS_REGION" {}
variable "teamcity_build_id" {}
variable "ONPREM_INSTALLER_URL" {}
variable "ONPREM_AWS_INSTANCE_SIZE" {}
variable "system_teamcity_buildType_id" {}
variable "dcos_security" {}
variable "password_hash" {}

variable "dcos_license_key_contents" {
  type = "string"
  default = ""
  description = "Defines content of license used for EE."
}

variable "variant" {
  type = "string"
  default = "open"
}

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
  dcos_variant              = "${var.variant}"
  dcos_security             = "${var.dcos_security}"
  dcos_license_key_contents = "${var.dcos_license_key_contents}"
  dcos_superuser_username = "testadmin"
  dcos_superuser_password_hash = "${var.password_hash}"
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
