provider "aws" {
}

data "aws_region" "current" {}

# Used to determine your public IP for forwarding rules
data "http" "whatismyip" {
  url = "http://whatismyip.akamai.com/"
}

locals {
  default_tags = {
    "owner"         = "${var.owner}"
    "expiration"    = "${var.expiration}"
    "build_id"      = "${var.build_id}"
    "build_type_id" = "${var.build_type}"
  }

  tags = merge(local.default_tags, var.tags)

  region_ami = length(var.aws_region_amis) > 0 ? lookup(var.aws_region_amis, data.aws_region.current.name, "no-ami-id-for-this-region") : ""
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

module "dcos" {
  source  = "dcos-terraform/dcos/aws"
  version = "~> 0.3.0"

  providers = {
    aws = aws
  }

  # allow every port >= 1024 https://jira.d2iq.com/browse/D2IQ-67041
  public_agents_allow_registered = true
  public_agents_allow_dynamic    = true

  cluster_name               = var.cluster_name
  cluster_name_random_string = true
  ssh_public_key_file        = ""
  ssh_public_key             = tls_private_key.ssh.public_key_openssh
  bootstrap_ssh_private_key  = tls_private_key.ssh.private_key_pem
  admin_ips                  = ["${data.http.whatismyip.body}/32"]

  num_masters        = var.num_masters
  num_private_agents = var.num_private_agents
  num_public_agents  = var.num_public_agents

  dcos_instance_os             = "centos_7.6"
  aws_ami                      = try(coalesce(var.aws_ami, local.region_ami), "")
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

resource "local_file" "ansible_inventory" {
  filename = "./inventory"

  content = <<EOF
[bootstraps]
${module.dcos.infrastructure_bootstrap_public_ip}
[masters]
${join("\n", module.dcos.infrastructure_masters_public_ips)}
[agents_private]
${join("\n", concat(
  module.gpuagent.private_ips,
  module.dcos.infrastructure_private_agents_private_ips,
))}
[agents_public]
${join("\n", module.dcos.infrastructure_public_agents_public_ips)}
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

resource "local_file" "ssh_private_key_file" {
  filename        = var.ssh_private_key_file_name
  file_permission = "0600"

  content = tls_private_key.ssh.private_key_pem
}


// currently kept for backward compatibility
# output "dcos_ui" {
#   description = "This is the load balancer address to access the DC/OS UI"
#   value       = "http://${module.dcos.masters-loadbalancer}/"
# }
#
# output "masters_public_ip" {
#   description = "This is the public masters IP to SSH"
#   value       = element(module.dcos.infrastructure.masters.public_ips, 0)
# }
#
# output "masters_private_ip" {
#   description = "This is the private masters IP address"
#   value       = element(module.dcos.infrastructure.masters.private_ips, 0)
# }
#
# output "private_agent_ips" {
#   description = "These are the IP addresses of all private agents"
#   value       = join(",", concat(module.dcos.infrastructure.private_agents.private_ips))
# }
#
# output "public_agent_ips" {
#   description = "These are the IP addresses of all public agents"
#   value       = join(",", module.dcos.infrastructure.public_agents.private_ips)
# }


// new outputs
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
