SHELL := /bin/bash -euo pipefail

export AWS_REGION ?= us-west-2
export TF_VAR_custom_dcos_download_path_win ?= https://downloads.dcos.io/dcos/testing/master/windows/dcos_generate_config_win.sh
export TF_VAR_variant ?= open
export OUTPUT_FILE ?= /dev/stdout

.DEFAULT_GOAL := test

.PHONY: maws
maws:
	$(eval $(shell maws login "eng-devprod"))

.PHONY: get-terraform
get-terraform:
	rm -rf ./terraform_0.11.14_linux_amd64.zip
	wget https://releases.hashicorp.com/terraform/0.11.14/terraform_0.11.14_linux_amd64.zip
	unzip ./terraform*.zip
	chmod +x terraform

# TODO (dcos-team): This should not be required Open DC/OS
.PHONY: dcos-set-license
dcos-set-license:
	@echo ${DCOS_LICENSE_CONTENTS} > license.txt

.PHONY: terraform-init
terraform-init:  get-terraform dcos-set-license
	./terraform init --upgrade

.PHONY: ssh-agent
ssh-agent:
	if [ -z "$$SSH_AUTH_SOCK" ] ; then \
	  eval $$(ssh-agent -s); \
	fi

.PHONY: ssh-keygen-add
ssh-keygen-add: ssh-agent
	ssh-keygen -t rsa -b 2048 -f ./tf-dcos-rsa.pem -q -N ""; \
	ssh-add ./tf-dcos-rsa.pem;

.PHONY: test
test: terraform-init ssh-keygen-add
	./terraform apply -auto-approve

.PHONY: output
output:
	./terraform output > ${OUTPUT_FILE}

.PHONY: destroy
destroy:
	./terraform destroy

.PHONY: clean
clean:
	rm -rf ./terraform
	rm -rf ./.terraform/
	rm -rf ./inventory
	rm -rf ./terraform.tfstate
	rm -rf ./terraform.tfstate.backup
	rm -rf ./terraform_0.11.14_linux_amd64.zip
	rm -rf ./*.pem
	rm -rf ./*.pub
	rm -rf ./license.txt


.PHONY: experiment
experiment:
	for number in 1 2 3 4 ; do \
		echo "make experiment..."; \
	done
