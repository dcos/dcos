provider "aws" {
  region = "us-east-1"
}

# Used to determine your public IP for forwarding rules
data "http" "whatismyip" {
  url = "http://whatismyip.akamai.com/"
}

locals {
  default_tags = {
    "owner"      = "slack:channel:mesosphere-org"
    "expiration" = "4h"
  }

  tags = merge(local.default_tags, var.tags)
}

resource "random_string" "dcosuser" {
  length  = 10
  special = false
  upper   = false
  number  = false
}

resource "tls_private_key" "ssh" {
  algorithm = "RSA"
  rsa_bits  = "4096"
}

##########################################################################
########################## DC/OS Infrastructure ##########################
##########################################################################

module "dcos" {
  source  = "dcos-terraform/dcos/aws"
  version = "~> 0.3.0"

  providers = {
    aws = aws
  }

  # allow every port >= 1024 https://jira.d2iq.com/browse/D2IQ-67041
  public_agents_allow_registered = true
  public_agents_allow_dynamic    = true

  cluster_name              = var.cluster_name
  ssh_public_key_file       = ""
  ssh_public_key            = tls_private_key.ssh.public_key_openssh
  bootstrap_ssh_private_key = tls_private_key.ssh.private_key_pem
  admin_ips                 = ["${data.http.whatismyip.body}/32", "82.194.127.1/32", "213.61.89.160/29", "4.35.161.16/30", "38.88.217.0/29", "38.88.217.0/29"]

  num_masters        = var.num_masters
  num_private_agents = var.num_private_agents
  num_public_agents  = var.num_public_agents

  dcos_instance_os             = "centos_7.6"
  bootstrap_instance_type      = "m5.xlarge"
  masters_instance_type        = var.masters_instance_type
  private_agents_instance_type = var.private_agents_instance_type
  public_agents_instance_type  = var.public_agents_instance_type

  dcos_variant              = var.dcos_variant
  dcos_version              = var.dcos_version
  dcos_image_commit         = var.dcos_image_commit
  dcos_license_key_contents = var.dcos_license_key_contents
  custom_dcos_download_path = var.custom_dcos_download_path
  dcos_calico_network_cidr  = "172.17.0.0/16"

  dcos_superuser_username = random_string.dcosuser.result
  dcos_security           = var.dcos_security
  open_admin_router       = true
  open_instance_ssh       = true

  additional_private_agent_ips = concat(module.gpuagent.private_ips)

  tags = local.tags
}

module "gpuagent" {
  source  = "dcos-terraform/private-agents/aws"
  version = "~> 0.3.0"

  providers = {
    aws = aws
  }

  cluster_name    = var.cluster_name
  hostname_format = "%[3]s-gpuagent%[1]d-%[2]s"

  aws_subnet_ids           = module.dcos.infrastructure_vpc_subnet_ids
  aws_security_group_ids   = [module.dcos.infrastructure_security_groups_internal, module.dcos.infrastructure_security_groups_admin]
  aws_key_name             = module.dcos.infrastructure_aws_key_name
  aws_instance_type        = var.gpu_agents_instance_type
  aws_iam_instance_profile = module.dcos.infrastructure_iam_agent_profile

  num_private_agents = var.num_gpu_agents

  tags = local.tags
}


output "cluster" {
  description = "This is the load balancer address to access the DC/OS UI"
  value       = module.dcos.masters-loadbalancer
}

output "public_agents" {
  description = "This is the load balancer address to access the DC/OS UI"
  value       = module.dcos.public-agents-loadbalancer
}

output "masters_dns_name" {
  description = "This is the load balancer address to access the DC/OS UI"
  value       = module.dcos.masters-loadbalancer
}

output "number_of_agents" {
  description = "The summarized number of private and public agents"
  value       = var.num_private_agents + var.num_public_agents + var.num_gpu_agents
}

output "number_of_private_agents" {
  description = "The summarized number of private"
  value       = var.num_private_agents + var.num_gpu_agents
}

output "number_of_public_agents" {
  description = "The number of public agents"
  value       = var.num_public_agents
}

output "number_of_masters" {
  description = "The number of masters"
  value       = var.num_masters
}

output "master_public_ips" {
  description = "agents private ips"
  value       = module.dcos.infrastructure_masters_public_ips
}

output "master_ips" {
  description = "agents private ips"
  value       = module.dcos.infrastructure_masters_private_ips
}

output "master_ips_cs" {
  description = "agents private ips"
  value       = join(",", module.dcos.infrastructure_masters_private_ips)
}

output "private_agents_ips" {
  description = "agents private ips"
  value = concat(
    module.gpuagent.private_ips,
    module.dcos.infrastructure_private_agents_private_ips,
  )
}

output "private_agents_ips_cs" {
  description = "agents private ips"
  value = join(",", concat(
    module.gpuagent.private_ips,
    module.dcos.infrastructure_private_agents_private_ips,
  ))
}

output "public_agents_ips" {
  description = "agents private ips"
  value       = module.dcos.infrastructure_public_agents_private_ips
}

output "public_agents_ips_cs" {
  description = "agents private ips"
  value       = join(",", module.dcos.infrastructure_public_agents_private_ips)
}


output "private_agents_public_ips" {
  description = "agents private ips"
  value = concat(
    module.gpuagent.public_ips,
    module.dcos.infrastructure_private_agents_public_ips,
  )
}
output "dcos_username" {
  description = "DC/OS Username"
  value       = random_string.dcosuser.result
}

output "dcos_password" {
  description = "DC/OS Password"
  value       = "dogfoodinit"
}

output "cluster_name" {
  description = "DC/OS Cluster name / prefix"
  value       = var.cluster_name
}

output "cluster_key" {
  description = "DC/OS SSH Private Key"
  value       = tls_private_key.ssh.private_key_pem
}

output "cluster_username" {
  description = "DC/OS SSH Username"
  # os and therefore username should be the same for masters,agents and public agents
  value = module.dcos.infrastructure_masters_os_user
}

output "integrationtest_vars" {
  description = "Variables running DC/OS Integrationtest"
  value       = <<EOF
MASTER_HOSTS="${join(",", module.dcos.infrastructure_masters_private_ips)}" SLAVE_HOSTS="${join(",", concat(module.gpuagent.private_ips, module.dcos.infrastructure_private_agents_private_ips, ))}" PUBLIC_SLAVE_HOSTS="${join(",", module.dcos.infrastructure_public_agents_private_ips)}"
EOF
}
