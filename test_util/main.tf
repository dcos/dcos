provider "aws" {}

#Linux Installer path - place url with "pull/PR#" or "master" suffix here:
variable "custom_dcos_download_path" {
  type = "string"
  default = "https://downloads.mesosphere.com/dcos-enterprise/testing/master/dcos_generate_config.ee.sh"
}

#Windows Installer path - place url with "pull/PR#" or "master" suffix here:
variable "custom_dcos_download_path_win" {
  type = "string"
  default = "https://downloads.mesosphere.com/dcos-enterprise/testing/master/windows/dcos_generate_config_win.ee.sh"
}

variable "variant" {
  type = "string"
  default = "open"
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

variable "windowsagent_num" {
  type = "string"
  default = "0"
  description = "Defines the number of Windows agents for the cluster."
}

variable "ssh_public_key_file" {
  type = "string"
  default = "~/.ssh/id_rsa.pub"
  description = "Defines the public key to log on the cluster."
}

variable "dcos_license_key_contents" {
  type = "string"
  default = ""
  description = "Defines content of license used for EE."
}

# Used to determine your public IP for forwarding rules
data "http" "whatismyip" {
  url = "http://whatismyip.akamai.com/"
}

resource "random_string" "password" {
  length = 6
  special = true
  override_special = "-"
}

locals {
  cluster_name = "generic-dcos-it-${random_string.password.result}"
}

module "dcos" {
  source  = "dcos-terraform/dcos/aws"
  version = "~> 0.2.0"

  providers = {
    aws = "aws"
  }

  tags {
    owner = "${var.owner}"
    expiration = "${var.expiration}"
  }

  cluster_name        = "${local.cluster_name}"
  ssh_public_key_file = "${var.ssh_public_key_file}"
  admin_ips           = ["${data.http.whatismyip.body}/32"]

  num_masters        = "1"
  num_private_agents = "1"
  num_public_agents  = "1"

  dcos_instance_os        = "centos_7.5"
  bootstrap_instance_type = "m4.xlarge"

  dcos_variant              = "${var.variant}"
  dcos_security             = "${var.dcos_security}"
  dcos_version              = "2.1.0-beta1"
  dcos_license_key_contents = "${var.dcos_license_key_contents}"
  ansible_bundled_container = "mesosphere/dcos-ansible-bundle:windows-beta-support"

  custom_dcos_download_path = "${var.custom_dcos_download_path}"

  # provide a SHA512 hashed password, here "deleteme"
  dcos_superuser_password_hash = "$6$rounds=656000$YSvuFmasQDXheddh$TpYlCxNHF6PbsGkjlK99Pwxg7D0mgWJ.y0hE2JKoa61wHx.1wtxTAHVRHfsJU9zzHWDoE08wpdtToHimNR9FJ/"
  dcos_superuser_username      = "demo-super"
  additional_windows_private_agent_ips       = ["${concat(module.windowsagent.private_ips)}"]
  additional_windows_private_agent_passwords = ["${concat(module.windowsagent.windows_passwords)}"]

  dcos_config = <<-EOF
enable_windows_agents: true
-EOF

ansible_additional_config = <<-EOF
dcos:
 download_win: "${var.custom_dcos_download_path_win}"
-EOF
}

module "windowsagent" {
  source  = "dcos-terraform/windows-instance/aws"
  version = "~> 0.2.0"

  tags {
    owner = "${var.owner}"
    expiration = "${var.expiration}"
  }

  cluster_name           = "${local.cluster_name}"
  hostname_format        = "%[3]s-winagent%[1]d-%[2]s"
  aws_subnet_ids         = ["${module.dcos.infrastructure.vpc.subnet_ids}"]
  aws_security_group_ids = ["${module.dcos.infrastructure.security_groups.internal}", "${module.dcos.infrastructure.security_groups.admin}"]
  aws_key_name           = "${module.dcos.infrastructure.aws_key_name}"

  # provide the number of windows agents that should be provisioned.
  num = "${var.windowsagent_num}"
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
[agents_windows]
${join("\n",formatlist("%s ansible_user=${module.windowsagent.os_user} ansible_password=%s", module.windowsagent.public_ips, module.windowsagent.windows_passwords))}
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
[agents_windows:vars]
ansible_connection=winrm
ansible_winrm_transport=basic
ansible_winrm_server_cert_validation=ignore
[agents:children]
agents_private
agents_public
agents_windows
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
    value       = "${join(",", concat(module.windowsagent.private_ips, module.dcos.infrastructure.private_agents.private_ips))}"
}

output "public_agent_ips" {
    description = "These are the IP addresses of all public agents"
    value       = "${join(",", module.dcos.infrastructure.public_agents.private_ips)}"
}

output "passwords" {
  description = "This is the load balancer address to access the DC/OS UI"
  value       = "${module.windowsagent.windows_passwords}"
}
