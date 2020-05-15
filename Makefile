# SHELL := /bin/bash

# Force Python stdout/err to be unbuffered to have immediate
# feedback in e.g. a TeamCity build environment.
export PYTHONUNBUFFERED="notemtpy"

WHEELHOUSE=/tmp/wheelhouse
PWD=$(shell pwd)

tree_variants ?=default installer

define RELEASE_CONFIG
storage: 
  local:
    kind: local_path
    path: $(PWD)/dcos-artifacts
options:
  preferred: local
  cloudformation_s3_url: https://s3-us-west-2.amazonaws.com/downloads.dcos.io/dcos
endef
export RELEASE_CONFIG

.PHONY: tox
tox:
	rm -rf dcos-release.config.yaml
	cp config/dcos-release.config.yaml dcos-release.config.yaml
	pip3 install tox && tox

.PHONY: dcos # TODO: make it a proper file target such as artifacts/dcos-generate-config.sh
dcos: pip dcos-release.config.yaml
	release --noop --local create `whoami` local_build $(tree_variants)

dcos-release.config.yaml:
	$(file >$@,$CONFIG) # Requires Make 4
	#echo "$$RELEASE_CONFIG" > $@

.PHONY: pip
pip:
	pip3 install -e $(PWD)
