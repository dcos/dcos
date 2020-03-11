SHELL := /bin/bash -euo pipefail

TERRAFORM_VERSION := 0.11.14
# TERRAFORM := TERRAFORM_VERSION=$(TERRAFORM_VERSION) bin/terraform
TERRAFORM := terraform

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
terraform-init: license.txt 
	$(TERRAFORM) init --upgrade

.PHONY: ssh-agent
ssh-agent:
	if [ -z "$$SSH_AUTH_SOCK" ] ; then \
	  eval $$(ssh-agent -s); \
	fi

# TODO: make sure ssh-agent is active
tf-dcos-rsa.pem: 
	ssh-keygen -t rsa -b 2048 -f $@ -q -N ""; \

.PHONY: cluster
cluster: terraform-init tf-dcos-rsa.pem 
	ssh-add ./tf-dcos-rsa.pem; \
	$(TERRAFORM) apply -auto-approve -var ssh_public_key_file=./tf-dcos-rsa.pem.pub -var windowsagent_num=1

cluster.json: # cluster
	$(TERRAFORM) output -json > $@ 

.PHONY: test # TODO: omit DCOS_ACS_TOKEN
test: cluster.json
	STATE=/Users/kjeschkies/src/dcos/test_util/terraform.tfstate
	cd ../packages/dcos-integration-test/extra; \
	MASTER_PUBLIC_IP="$(shell terraform output -state=$(STATE) masters_public_ip)" \
	MASTERS_PRIVATE_IPS="$(shell echo '172.16.0.130')" \
	PRIVATE_AGENTS_PRIVATE_IPS="$(shell terraform output -state=/Users/kjeschkies/src/dcos/test_util/terraform.tfstate private_agent_ips)" \
	PUBLIC_AGENTS_PRIVATE_IPS="$(shell terraform output -state=/Users/kjeschkies/src/dcos/test_util/terraform.tfstate public_agent_ips)" \
	DCOS_ACS_TOKEN="$(shell dcos config show core.dcos_acs_token)" \
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
	rm -rf ./terraform_0.11.14_linux_amd64.zip
	rm -rf ./*.pem
	rm -rf ./*.pub
	rm -rf ./license.txt
