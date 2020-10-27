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
  default = ""
}

variable "dcos_variant" {
  default = "open"
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
