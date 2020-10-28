SHELL := /bin/bash -euo pipefail

TERRAFORM_VERSION := 0.12.26
OS ?= $(shell uname|tr A-Z a-z)

# Path to Terraform binary.
TERRAFORM ?= ./terraform.bin

export AWS_REGION ?= us-west-2
export TF_VAR_variant ?= open

export TF_VAR_cluster_name ?= generic-dcos

ifneq ($(TF_VAR_variant), open)
	DCOS_USER_PASSWORD_ENV := DCOS_LOGIN_UNAME='demo-super' DCOS_LOGIN_PW='deleteme'
endif

SSH_KEY ?= ./tf-dcos-rsa.pem
export TF_VAR_ssh_private_key_file_name := $(SSH_KEY)

ifdef DCOS_LICENSE_CONTENTS
	export TF_VAR_dcos_license_key_contents := $(DCOS_LICENSE_CONTENTS)
endif

diagnostics_bundle_file = diagnostics-$(shell date +%Y-%m-%d_%H-%M-%S).zip

################################### TARGETS ###################################

.DEFAULT_GOAL := test

terraform.initialized: $(TERRAFORM) main.tf
	@echo "##teamcity[blockOpened name='terraform-init' description='Terraform initialization']"
	$(TERRAFORM) init -input=false --upgrade | tee terraform.log
	mv terraform.log $@
	@echo "##teamcity[blockClosed name='terraform-init']"

cluster.json: terraform.initialized
	@echo "##teamcity[blockOpened name='terraform-apply' description='Terraform cluster creation']"
	$(TERRAFORM) apply -auto-approve -input=false
	$(TERRAFORM) output -json > $@.work
	@echo "##teamcity[blockClosed name='terraform-apply']"
	mv $@.work $@

.PHONY: test
test: cluster.json
ifdef OVERWRITE_INTEGRATION_TESTS
		$(info Use local integration tests)
		rsync -avz --rsync-path="sudo rsync" -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY)" ../packages/dcos-integration-test/extra/* $(shell jq '.cluster_username.value' $<)@$(shell jq '.master_public_ips.value[0]' $<):/opt/mesosphere/active/dcos-integration-test/
endif
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) $(shell jq '.cluster_username.value' $<)@$(shell jq '.master_public_ips.value[0]' $<) -- \
		"cd /opt/mesosphere/active/dcos-integration-test && \
		MASTER_PUBLIC_IP=$(shell jq '.master_public_ips.value[0]' $<) \
		MASTERS_PRIVATE_IPS=$(shell jq '.master_ips_cs.value' $<) \
		MASTER_HOSTS=$(shell jq '.master_ips.value[0]' $<) \
		PRIVATE_AGENTS_PRIVATE_IPS=$(shell jq '.private_agents_ips_cs.value' $<) \
		SLAVE_HOSTS=$(shell jq '.private_agents_ips_cs.value' $<) \
		PUBLIC_AGENTS_PRIVATE_IPS=$(shell jq '.public_agents_ips_cs.value' $<) \
		PUBLIC_SLAVE_HOSTS=$(shell jq '.public_agents_ips_cs.value' $<) \
		$(DCOS_USER_PASSWORD_ENV) \
		timeout -k 10m --preserve-status 90m \
		dcos-shell pytest -vv --teamcity --log-level=DEBUG $(PYTEST_EXTRA_ARGS)"

.PHONY: ssh
ssh: cluster.json
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) $(shell jq '.cluster_username.value' $<)@$(shell jq '.master_public_ips.value[0]' $<)

.PHONY: diagnostics
diagnostics: $(diagnostics_bundle_file)

.PHONY: destroy
destroy:
	@echo "##teamcity[blockOpened name='terraform-destroy' description='Terraform cluster teardown']"
	$(TERRAFORM) destroy -auto-approve
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
	rm -rf ./terraform.initialized
	rm -rf $(TERRAFORM)


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
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) $(shell jq '.cluster_username.value' $<)@$(shell jq '.master_public_ips.value[0]' $<) -- \
		"$(curl_cmd) -X PUT $(diagnostics_api)/$*"
	touch $@

# Wait until diagnostics bundle is ready.
diagnostics-%.done: cluster.json diagnostics-%.started
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) $(shell jq '.cluster_username.value' $<)@$(shell jq '.master_public_ips.value[0]' $<) -- \
		"$(curl_cmd) -s $(diagnostics_api)/$* -o status.json; \
		until jq '.status' status.json | grep -q 'Done'; do cat status.json; $(curl_cmd) -s $(diagnostics_api)/$* -o status.json; sleep 5; done;"
	rm diagnostics-$*.started || true
	touch $@

# Download diagnostics bundle.
diagnostics-%.zip : cluster.json diagnostics-%.done
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) $(shell jq '.cluster_username.value' $<)@$(shell jq '.master_public_ips.value[0]' $<) -- \
		"$(curl_cmd) $(diagnostics_api)/$*/file -o $@"
	scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) $(shell jq '.cluster_username.value' $<)@$(shell jq '.master_public_ips.value[0]' $<):/home/centos/$@ $@.work
	rm diagnostics-$*.done || true
	mv $@.work $@
	@echo "##teamcity[blockClosed name='diagnostics-bundle']"


################################### HELPERS ###################################

# Provision Terraform if not available.

terraform_$(TERRAFORM_VERSION)_$(OS)_amd64.zip:
	wget -nv https://releases.hashicorp.com/terraform/$(TERRAFORM_VERSION)/$@

$(TERRAFORM): terraform_$(TERRAFORM_VERSION)_$(OS)_amd64.zip
	unzip -n $<;
	mv ./terraform $(TERRAFORM);
	chmod +x $(TERRAFORM);
