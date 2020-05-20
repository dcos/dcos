SHELL := /bin/bash -euo pipefail

TERRAFORM_VERSION := 0.11.14
OS ?= $(shell uname|tr A-Z a-z)

# Path to Terraform binary.
TERRAFORM ?= ./terraform

export AWS_REGION ?= us-west-2
export TF_VAR_custom_dcos_download_path ?= https://downloads.dcos.io/dcos/testing/master/dcos_generate_config.sh
export TF_VAR_variant ?= open

ifneq ($(TF_VAR_variant), open)
	DCOS_USER_PASSWORD_ENV := DCOS_LOGIN_UNAME='demo-super' DCOS_LOGIN_PW='deleteme'
endif

SSH_KEY ?= ./tf-dcos-rsa.pem

ifndef DCOS_LICENSE_CONTENTS
$(error DCOS_LICENSE_CONTENTS is not set)
endif

diagnostics_bundle_file = diagnostics-$(shell date +%Y-%m-%d_%H-%M-%S).zip

################################### TARGETS ###################################

.DEFAULT_GOAL := test

terraform.initialized: $(TERRAFORM) main.tf
	@echo "##teamcity[blockOpened name='terraform-init' description='Terraform initialization']"
	$(TERRAFORM) init -input=false --upgrade | tee terraform.log
	mv terraform.log $@
	@echo "##teamcity[blockClosed name='terraform-init']"

$(SSH_KEY):
	ssh-keygen -t rsa -b 2048 -f $@ -q -N ""

cluster.json: $(SSH_KEY) terraform.initialized
	@echo "##teamcity[blockOpened name='terraform-apply' description='Terraform cluster creation']"
	if [ -z "$$SSH_AUTH_SOCK" ]; then eval $$(ssh-agent -s); fi; \
	ssh-add "$(SSH_KEY)"; \
	$(TERRAFORM) apply -auto-approve -input=false \
		-var ssh_public_key_file="$(SSH_KEY).pub" \
		-var dcos_license_key_contents=$(DCOS_LICENSE_CONTENTS)
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
		timeout -k 10m --preserve-status 90m \
		dcos-shell pytest -vv --teamcity --log-level=DEBUG"

.PHONY: ssh
ssh: cluster.json
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) centos@$(shell jq '.masters_public_ip.value' $<)

.PHONY: diagnostics
diagnostics: $(diagnostics_bundle_file)

.PHONY: destroy
destroy:
	@echo "##teamcity[blockOpened name='terraform-destroy' description='Terraform cluster teardown']"
	$(TERRAFORM) destroy -auto-approve \
		-var ssh_public_key_file="$(SSH_KEY).pub" \
		-var dcos_license_key_contents=$(DCOS_LICENSE_CONTENTS)
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


################################# DISGNOSTICS #################################

diagnostics_api = localhost:1050/system/health/v1/diagnostics
curl_cmd = curl
ifneq ($(TF_VAR_variant), open)
	diagnostics_api = --unix-socket /var/run/dcos/dcos-diagnostics.sock http:/system/health/v1/diagnostics
	curl_cmd = sudo curl
endif

# Start diagnostics bundle creation.
diagnostics-%.started: cluster.json
	@echo "##teamcity[blockOpened name='diagnostics-bundle' description='Download Diagnostics bundle']"
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) centos@$(shell jq '.masters_public_ip.value' $<) -- \
		"$(curl_cmd) -X PUT $(diagnostics_api)/$*"
	touch $@

# Wait until diagnostics bundle is ready.
diagnostics-%.done: cluster.json diagnostics-%.started 
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) centos@$(shell jq '.masters_public_ip.value' $<) -- \
		"$(curl_cmd) -s $(diagnostics_api)/$* -o status.json; \
		until jq '.status' status.json | grep -q 'Done'; do cat status.json; $(curl_cmd) -s $(diagnostics_api)/$* -o status.json; sleep 5; done;"
	rm diagnostics-$*.started || true
	touch $@

# Download diagnostics bundle.
diagnostics-%.zip : cluster.json diagnostics-%.done
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) centos@$(shell jq '.masters_public_ip.value' $<) -- \
		"$(curl_cmd) $(diagnostics_api)/$*/file -o $@"
	scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) centos@$(shell jq '.masters_public_ip.value' $<):/home/centos/$@ $@.work
	rm diagnostics-$*.done || true
	mv $@.work $@
	@echo "##teamcity[blockClosed name='diagnostics-bundle']"


################################### HELPERS ###################################

# Provision Terraform if not available.

terraform_$(TERRAFORM_VERSION)_$(OS)_amd64.zip:
	wget -nv https://releases.hashicorp.com/terraform/$(TERRAFORM_VERSION)/$@

$(TERRAFORM): terraform_$(TERRAFORM_VERSION)_$(OS)_amd64.zip
	unzip -n $<;
	chmod +x terraform;

