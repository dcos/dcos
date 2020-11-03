SHELL := /bin/bash -euo pipefail

include terraform.mk
include dcos.mk
include diagnostics.mk

.PHONY: test
test: dcos-test

.PHONY: destroy
destroy: dcos-destroy

.PHONY: clean
clean: dcos-clean
