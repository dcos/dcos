TF_VAR_dcos_version ?= stable
SCENARIO ?= centos-7.8.2003/defaults

include ../test_util/terraform.mk
include ../test_util/dcos.mk
include ../test_util/diagnostics.mk


%.tf:
	ln -Fs ../test_util/*.tf .

terraform.tfvars:
	cp scenarios/$(SCENARIO)/terraform.tfvars .

.PHONY: test
test: %.tf terraform.tfvars dcos-test

.PHONY: destroy
destroy: dcos-destroy

.PHONY: qualification-clean
qualification-clean:
	rm -f ./*.tf
	rm -f ./terraform.tfvars

.PHONY: clean
clean: qualification-clean dcos-clean
