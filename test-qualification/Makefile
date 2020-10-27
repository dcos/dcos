DCOS_UPGRADE_BASE ?= stable

INTEGRATION_TEST_PATTERN ?= not test_blkio_stats and not test_task_prom_metrics_not_filtered and not test_prom_metrics_containers_app_bridge and not test_dcos_cni_l4lb

CLUSTER_NAME ?= qualupgr$(shell date +%Y%m%d)

# -s log output as it goes not in the end.
define exec_integrationtestgroup
    ssh -i ./test_id_rsa $(shell terraform output cluster_username)@$(shell terraform output -json master_public_ips | jq -r '.[0]') 'source /opt/mesosphere/environment.export && cd `find /opt/mesosphere/active/ -name dcos-integration-test* | sort | tail -n 1` && $(shell terraform output integrationtest_vars) pytest -v `python get_test_group.py $(1)`'
endef

define exec_integrationtestpattern
    ssh -i ./test_id_rsa $(shell terraform output cluster_username)@$(shell terraform output -json master_public_ips | jq -r '.[0]') 'source /opt/mesosphere/environment.export && cd `find /opt/mesosphere/active/ -name dcos-integration-test* | sort | tail -n 1` && $(shell terraform output integrationtest_vars) pytest -v -s -k "$(1)"'
endef

.PHONY: init
init:
	terraform init ./

.PHONY: upgrade
upgrade: init upgrade-base upgrade-target upgrade-destroy
  # DCOS_UPGRADE_BASE=2.1.0
  # DCOS_UPGRADE_TARGET_URL="<buildurl>"
  # DCOS_UPGRADE_TARGET_VERSION="<build version specifier>"

.PHONY: ssh-key
ssh-key:
	terraform output cluster_key > ./test_id_rsa
	chmod 600 ./test_id_rsa


.PHONY: upgrade-base
upgrade-base:
	terraform apply -auto-approve -var "dcos_version=$(DCOS_UPGRADE_BASE)" -var "cluster_name=$(CLUSTER_NAME)"

.PHONY: upgrade-target
upgrade-target:
	terraform apply -auto-approve -var "dcos_version=$(DCOS_UPGRADE_TARGET_VERSION)" -var "custom_dcos_download_path=$(DCOS_UPGRADE_TARGET_URL)" -var "cluster_name=$(CLUSTER_NAME)"

.PHONY: upgrade-preupgrade-runtasks
upgrade-preupgrade-runtasks:
	# start some tasks to be verified after upgrade

.PHONY: upgrade-verify-cluster
upgrade-verify-cluster:
	# verify the cluster state after upgrade. Amount of agents. GPUs avail? and so on

.PHONY: upgrade-destroy
upgrade-destroy: init
	terraform destroy -auto-approve -var "cluster_name=$(CLUSTER_NAME)"

.PHONY: upgrade-test
upgrade-test: upgrade-base upgrade-preupgrade-runtasks upgrade-target upgrade-verify-cluster integration-test-pattern upgrade-destroy


.PHONY: integration-test
integration-test: ssh-key integration-test-group1 integration-test-group2 integration-test-group3 integration-test-group4

.PHONY: integration-test-pattern
integration-test-pattern: ssh-key
	$(call exec_integrationtestpattern,$(INTEGRATION_TEST_PATTERN))

.PHONY: integration-test-group1
integration-test-group1: ssh-key
	$(call exec_integrationtestgroup,group_1)
.PHONY: integration-test-group2
integration-test-group2: ssh-key
	$(call exec_integrationtestgroup,group_2)
.PHONY: integration-test-group3
integration-test-group3: ssh-key
	$(call exec_integrationtestgroup,group_3)
.PHONY: integration-test-group4
integration-test-group4: ssh-key
	$(call exec_integrationtestgroup,group_4)
