SHELL := /bin/bash -euo pipefail

TERRAFORM_VERSION := 0.11.14
OS ?= $(shell uname|tr A-Z a-z)

# Path to Terraform binary.
TERRAFORM ?= ./terraform

export AWS_REGION ?= us-west-2
export TF_VAR_custom_dcos_download_path ?= https://downloads.dcos.io/dcos/testing/master/dcos_generate_config.sh
export TF_VAR_custom_dcos_download_path_win ?= https://downloads.dcos.io/dcos/testing/master/windows/dcos_generate_config_win.sh
export TF_VAR_variant ?= open

ifneq ($(TF_VAR_variant), open)
	DCOS_USER_PASSWORD_ENV := DCOS_LOGIN_UNAME='demo-super' DCOS_LOGIN_PW='deleteme'
endif

SSH_KEY ?= ./tf-dcos-rsa.pem

ifndef DCOS_LICENSE_CONTENTS 
$(error DCOS_LICENSE_CONTENTS is not set)
endif

################################### TARGETS ################################### 

.DEFAULT_GOAL := test

license.txt:
	@echo ${DCOS_LICENSE_CONTENTS} > $@

.terraform: license.txt $(TERRAFORM) main.tf
	@echo "##teamcity[blockOpened name='terraform-init' description='Terraform initialization']"
	$(TERRAFORM) init -input=false --upgrade
	@echo "##teamcity[blockClosed name='terraform-init']"

$(SSH_KEY):
	ssh-keygen -t rsa -b 2048 -f $@ -q -N ""

cluster.json: $(SSH_KEY) .terraform
	@echo "##teamcity[blockOpened name='terraform-apply' description='Terraform cluster creation']"
	if [ -z "$$SSH_AUTH_SOCK" ]; then eval $$(ssh-agent -s); fi; \
	ssh-add "$(SSH_KEY)"; \
	$(TERRAFORM) apply -auto-approve -input=false -var ssh_public_key_file="$(SSH_KEY).pub" -var windowsagent_num=1
	$(TERRAFORM) output -json > $@.work
	@echo "##teamcity[blockClosed name='terraform-apply']"
	mv $@.work $@

.PHONY: test
test: cluster.json
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) centos@$(shell jq '.masters_public_ip.value' $<) -- \
		"cd /opt/mesosphere/active/dcos-integration-test && \
		MASTER_PUBLIC_IP=$(shell jq '.masters_public_ip.value' $<) \
		MASTERS_PRIVATE_IPS=$(shell jq '.masters_private_ip.value' $<) \
		MASTER_HOSTS=$(shell jq '.masters_private_ip.value' $<) \
		PRIVATE_AGENTS_PRIVATE_IPS=$(shell jq '.private_agent_ips.value' $<) \
		SLAVE_HOSTS=$(shell jq '.private_agent_ips.value' $<) \
		PUBLIC_AGENTS_PRIVATE_IPS=$(shell jq '.public_agent_ips.value' $<) \
		PUBLIC_SLAVE_HOSTS=$(shell jq '.public_agent_ips.value' $<) \
		$(DCOS_USER_PASSWORD_ENV) \
		dcos-shell pytest -vv --teamcity --log-level=DEBUG --windows-only"

.PHONY: ssh 
ssh: cluster.json
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) centos@$(shell jq '.masters_public_ip.value' $<)

.PHONY: destroy
destroy: cluster.json
	@echo "##teamcity[blockOpened name='terraform-destroy' description='Terraform cluster teardown']"
	$(TERRAFORM) destroy -auto-approve -var ssh_public_key_file="$(SSH_KEY).pub";
	rm cluster.json || true;
	@echo "##teamcity[blockClosed name='terraform-destroy']"

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

################################### HELPERS ################################### 

# Provision Terraform if not available.

terraform_$(TERRAFORM_VERSION)_$(OS)_amd64.zip:
	wget -nv https://releases.hashicorp.com/terraform/$(TERRAFORM_VERSION)/$@

$(TERRAFORM): terraform_$(TERRAFORM_VERSION)_$(OS)_amd64.zip
	unzip -n $<;
	chmod +x terraform;

