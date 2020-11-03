variable "cluster_name" {
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "dcos_version" {
  default = "stable"
}

variable "custom_dcos_download_path" {
  description = "Linux Installer path - place url with 'pull/PR#' or 'master' suffix here:"
  default     = ""
  //default = "https://downloads.dcos.io/dcos/testing/master/dcos_generate_config.sh"
}

variable "dcos_variant" {
  default = "open"
}

variable "owner" {
  default = "slack:channel:mesosphere-org"
}

variable "expiration" {
  default = "4h"
}

variable "build_id" {
  default     = ""
  description = "Build ID from CI."
}

variable "build_type" {
  default     = ""
  description = "Build type from CI."
}

variable "dcos_license_key_contents" {
  default = ""
}

variable "dcos_image_commit" {
  default = ""
}

variable "dcos_security" {
  default = "permissive"
}

variable "num_masters" {
  default = 1
}

variable "masters_instance_type" {
  default = "m5.2xlarge"
}

variable "num_private_agents" {
  default = 2
}

variable "private_agents_instance_type" {
  default = "m5.2xlarge"
}

variable "num_public_agents" {
  default = 1
}

variable "public_agents_instance_type" {
  default = "m5.2xlarge"
}

variable "num_gpu_agents" {
  default = 0
}

variable "gpu_agents_instance_type" {
  default = "p2.xlarge"
}

variable "ssh_private_key_file_name" {
  default = "./tf-dcos-rsa.pem"
}

variable "aws_ami" {
  default = null
}

variable "aws_region_amis" {
  default = {}
}
