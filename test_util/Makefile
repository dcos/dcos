SHELL := /bin/bash -euo pipefail

TERRAFORM_VERSION := 0.11.4
TERRAFORM := TERRAFORM_VERSION=$(TERRAFORM_VERISON) bin/terraform

export AWS_REGION ?= us-west-2
export TF_VAR_custom_dcos_download_path_win ?= https://downloads.dcos.io/dcos/testing/master/windows/dcos_generate_config_win.sh
export TF_VAR_variant ?= open
export OUTPUT_FILE ?= /dev/stdout

.DEFAULT_GOAL := test

license.txt:
	@echo ${DCOS_LICENSE_CONTENTS} > $@

.PHONY: terraform-init
terraform-init: license.txt 
	$(TERRAFORM) init --upgrade

.PHONY: ssh-agent
ssh-agent:
	if [ -z "$$SSH_AUTH_SOCK" ] ; then \
	  eval $$(ssh-agent -s); \
	fi

./tf-dcos-rsa.pem: ssh-agent
	ssh-keygen -t rsa -b 2048 -f $@ -q -N ""; \
	ssh-add $@;

.PHONY: test
test: terraform-init ./tf-dcos-rsa.pem 
	$(TERRAFORM) apply -auto-approve

.PHONY: output
output:
	$(TERRAFORM) output > ${OUTPUT_FILE}

.PHONY: destroy
destroy:
	$(TERRAFORM) destroy

.PHONY: clean
clean:
	rm -rf ./.terraform/
	rm -rf ./inventory
	rm -rf ./terraform.tfstate
	rm -rf ./terraform.tfstate.backup
	rm -rf ./terraform_0.11.14_linux_amd64.zip
	rm -rf ./*.pem
	rm -rf ./*.pub
	rm -rf ./license.txt
