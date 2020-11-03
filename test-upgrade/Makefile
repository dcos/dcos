DCOS_UPGRADE_BASE_VERSION ?= 2.1
DCOS_UPGRADE_TARGET_VERSION ?= 2.2

include ../test_util/terraform.mk
include ../test_util/dcos.mk
include ../test_util/diagnostics.mk

%.tf:
	ln -Fs ../test_util/*.tf .

terraform.tfvars: %.tf
	echo dcos_version=$(DCOS_UPGRADE_BASE_VERSION) >> $@
ifdef DCOS_UPGRADE_BASE_URL
	echo "custom_dcos_download_path=$(DCOS_UPGRADE_BASE_URL)" >> $@
endif

upgrade-base-pretest.json: terraform.tfvars cluster.json
	@echo '{"foo": "bar"}' > $@

upgrade.auto.tfvars: upgrade-base-pretest.json
	echo dcos_version=$(DCOS_UPGRADE_TARGET_VERSION) >> $@
ifdef DCOS_UPGRADE_BASE_URL
	echo custom_dcos_download_path=$(DCOS_UPGRADE_TARGET_URL) >> $@
endif

cluster-upgrade.json: upgrade.auto.tfvars
	$(call terraform_apply,$@)

.PHONY: upgrade-target-test
upgrade-target-test: cluster-upgrade.json
	jq . $<

.PHONY: test
test: upgrade-target-test

.PHONY: clean
clean: dcos-clean
	rm -rf ./*.tf
	rm -rf ./cluster-upgrade.json
	rm -rf ./upgrade-base-pretest.json
	rm -rf ./upgrade.auto.tfvars

.PHONY: destroy
destroy: dcos-destroy
	rm -rf ./cluster-upgrade.json
