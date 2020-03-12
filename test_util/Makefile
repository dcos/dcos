SHELL := /bin/bash -euo pipefail

TERRAFORM_VERSION := 0.11.14
# Path to Terraform binary.
TERRAFORM ?= ./terraform
OS ?= $(shell uname|tr A-Z a-z)

export AWS_REGION ?= us-west-2
export TF_VAR_custom_dcos_download_path ?= https://downloads.dcos.io/dcos/testing/master/dcos_generate_config.sh
export TF_VAR_custom_dcos_download_path_win ?= https://downloads.dcos.io/dcos/testing/master/windows/dcos_generate_config_win.sh
export TF_VAR_variant ?= open

ifndef DCOS_LICENSE_CONTENTS 
$(error DCOS_LICENSE_CONTENTS is not set)
endif

.DEFAULT_GOAL := test

license.txt:
	@echo ${DCOS_LICENSE_CONTENTS} > $@

.PHONY: terraform-init
terraform-init: license.txt $(TERRAFORM)
	$(TERRAFORM) init --upgrade

.PHONY: ssh-agent
ssh-agent:
	if [ -z "$$SSH_AUTH_SOCK" ] ; then \
	  eval $$(ssh-agent -s); \
	fi

tf-dcos-rsa.pem: ssh-agent
	ssh-keygen -t rsa -b 2048 -f $@ -q -N ""; \

.PHONY: cluster
cluster: terraform-init tf-dcos-rsa.pem 
	ssh-add ./tf-dcos-rsa.pem; \
	$(TERRAFORM) apply -auto-approve -var ssh_public_key_file=./tf-dcos-rsa.pem.pub -var windowsagent_num=1

cluster.json: cluster
	$(TERRAFORM) output -json > $@ 

.PHONY: test
test: cluster.json
	cd ../packages/dcos-integration-test/extra; \
	MASTER_PUBLIC_IP=$(shell jq '.masters_public_ip.value' $<) \
	MASTERS_PRIVATE_IPS=$(shell jq '.masters_private_ip.value' $<) \
	PRIVATE_AGENTS_PRIVATE_IPS=$(shell jq '.private_agent_ips.value' $<) \
	PUBLIC_AGENTS_PRIVATE_IPS=$(shell jq '.public_agent_ips.value' $<) \
	DCOS_SSH_USER=centos \
	pytest -v -x --capture=no --full-trace --log-level=DEBUG test_applications.py::test_if_marathon_app_can_be_deployed

.PHONY: destroy
destroy:
	$(TERRAFORM) destroy -auto-approve

.PHONY: clean
clean:
	rm -rf ./.terraform/
	rm -rf ./inventory
	rm -rf ./terraform.tfstate
	rm -rf ./terraform.tfstate.backup
	rm -rf ./terraform_*.zip
	rm -rf ./*.pem
	rm -rf ./*.pub
	rm -rf ./license.txt

# Provision Terraform is not available.

terraform_$(TERRAFORM_VERSION)_$(OS)_amd64.zip:
	wget -nv https://releases.hashicorp.com/terraform/$(TERRAFORM_VERSION)/$@

$(TERRAFORM): terraform_$(TERRAFORM_VERSION)_$(OS)_amd64.zip
	unzip -n $<;
	chmod +x terraform;
