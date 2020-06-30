variable "AWS_REGION" {
  type = "string"
  default = "us-west-2"
}

variable "custom_dcos_download_path" {
  type = "string"
  default = "https://downloads.mesosphere.com/dcos-enterprise/testing/master/dcos_generate_config.ee.sh"
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

provider "aws" {
  region = "${var.AWS_REGION}"
}

# Used to determine your public IP for forwarding rules
data "http" "whatismyip" {
  url = "http://whatismyip.akamai.com/"
}

resource "random_string" "password" {
  length = 12
  special = false
}

locals {
  cluster_name = "generic-dcos-it-${random_string.password.result}"
}

module "dcos" {
  source  = "dcos-terraform/dcos/aws"
  version = "~> 0.2.10"

  providers = {
    aws = "aws"
  }

  tags {
    owner = "${var.owner}"
    expiration = "${var.expiration}"
    build_id = "${var.build_id}"
    build_type_id = "${var.build_type}"
  }

  cluster_name        = "${local.cluster_name}"
  ssh_public_key_file = "${var.ssh_public_key_file}"
  admin_ips           = ["${data.http.whatismyip.body}/32"]

  num_masters        = "1"
  num_private_agents = "2"
  num_public_agents  = "1"

  dcos_instance_os    = "centos_7.5"

  bootstrap_instance_type = "${var.instance_type}"
  masters_instance_type  = "${var.instance_type}"
  private_agents_instance_type = "${var.instance_type}"
  public_agents_instance_type = "${var.instance_type}"
  #AVAILABILITYZONES

  dcos_calico_network_cidr = "172.17.0.0/16"
  dcos_variant              = "${var.variant}"
  dcos_security             = "${var.dcos_security}"
  dcos_license_key_contents = "${var.dcos_license_key_contents}"

  custom_dcos_download_path = "${var.custom_dcos_download_path}"

  dcos_superuser_username = "testadmin"
  dcos_superuser_password_hash = "${var.password_hash}"
}

resource "local_file" "ansible_inventory" {
  filename = "./inventory"

  content = <<EOF
[bootstraps]
${module.dcos.infrastructure.bootstrap.public_ip}
[masters]
${join("\n", module.dcos.infrastructure.masters.public_ips)}
[agents_private]
${join("\n", module.dcos.infrastructure.private_agents.public_ips)}
[agents_public]
${join("\n", module.dcos.infrastructure.public_agents.public_ips)}
[bootstraps:vars]
node_type=bootstrap
[masters:vars]
node_type=master
dcos_legacy_node_type_name=master
[agents_private:vars]
node_type=agent
dcos_legacy_node_type_name=slave
[agents_public:vars]
node_type=agent_public
dcos_legacy_node_type_name=slave_public
[agents:children]
agents_private
agents_public
[dcos:children]
bootstraps
masters
agents
agents_public
EOF
}

output "dcos_ui" {
  description = "This is the load balancer address to access the DC/OS UI"
  value       = "http://${module.dcos.masters-loadbalancer}/"
}

output "masters_public_ip" {
    description = "This is the public masters IP to SSH"
    value       = "${element(module.dcos.infrastructure.masters.public_ips, 0)}"
}

output "masters_private_ip" {
    description = "This is the private masters IP address"
    value       = "${element(module.dcos.infrastructure.masters.private_ips, 0)}"
}

output "private_agent_ips" {
    description = "These are the IP addresses of all private agents"
    value       = "${join(",", concat(module.dcos.infrastructure.private_agents.private_ips))}"
}

output "public_agent_ips" {
    description = "These are the IP addresses of all public agents"
    value       = "${join(",", module.dcos.infrastructure.public_agents.private_ips)}"
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