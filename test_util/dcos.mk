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

define terraform_apply
	@echo "##teamcity[blockOpened name='terraform-apply' description='Terraform cluster creation']"
	$(TERRAFORM) apply -auto-approve -input=false
	$(TERRAFORM) output -json > $1.work
	@echo "##teamcity[blockClosed name='terraform-apply']"
	mv $1.work $1
endef

.DEFAULT_GOAL := test

cluster.json: terraform.initialized
	$(call terraform_apply,$@)

.PHONY: dcos-test
dcos-test: cluster.json
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


.PHONY: dcos-destroy
dcos-destroy:
	@echo "##teamcity[blockOpened name='terraform-destroy' description='Terraform cluster teardown']"
	$(TERRAFORM) destroy -auto-approve || $(TERRAFORM) destroy -auto-approve -refresh=false
	rm cluster.json || true;
	@echo "##teamcity[blockClosed name='terraform-destroy']"

.PHONY: dcos-clean
dcos-clean:
	rm -rf ./.terraform/
	rm -rf ./inventory
	rm -rf ./terraform.tfstate
	rm -rf ./terraform.tfstate.backup
	rm -rf ./terraform_*.zip
	rm -rf ./*.pem
	rm -rf ./*.pub
	rm -rf ./terraform.initialized
	rm -rf $(TERRAFORM)
