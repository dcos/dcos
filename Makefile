SHELL := /bin/bash

# Force Python stdout/err to be unbuffered to
# have immediate feedback in TeamCity build logs.
export PYTHONUNBUFFERED="notemtpy"

WHEELHOUSE=/tmp/wheelhouse
DIR=$(shell pwd)

.PHONY: tox
tox:
	rm -rf dcos-release.config.yaml
	cp config/dcos-release.config.yaml dcos-release.config.yaml
	pip install tox && tox

.PHONY: dcos # TODO: make it a proper file target such as artifacts/dcos-generate-config.sh
dcos: $(WHEELHOUSE) dcos-release.config.yaml
	release create $(TAG) $(TAG) $(tree_variants)

	mkdir -p artifacts
	cp -r wheelhouse artifacts/

	rm -rf artifacts/dcos_generate_config.*

dcos-release.config.yaml:
	cp config/dcos-release.config.yaml dcos-release.config.yaml

$(WHEELHOUSE):
	# TODO: preinstall pip
	curl -O https://bootstrap.pypa.io/get-pip.py && /usr/bin/python3 get-pip.py && rm get-pip.py

	# NOTE: If the directory already exists that is indeed a hard error. Should be
	# cleaned up between builds to guarantee we get the artifacts we expect.
	mkdir -p $@
	
	# Make a clean copy of pkgpanda so the python artifacts build fast
	pushd $(DIR) && \
		rm -rf ext/dcos-image && git clone "file://$(DIR)" ext/dcos-image && \
		git -C ext/dcos-image checkout -qf $(shell git rev-parse --verify HEAD^{commit}) && \
	popd
	
	# We have wheel as a dependency since we use it to build the wheels
	pip install wheel
	
	# Download distro independent artifacts
	pip download -d $@ $(DIR)/ext/dcos-image
	
	# Make the wheels, they will be output into the folder `wheelhouse` by default.
	pip wheel --wheel-dir=$@ --no-index --find-links=$@ $(DIR)/ext/dcos-image
	
	# Install the wheels
	pip install --no-index --find-links=$@ dcos-image
	
	# Cleanup the checkout
	rm -rf $(DIR)/ext/dcos-image

.PHONY: clean
clean:
	# cleanup from previous builds
	# *active.json and *.bootstrap.tar.xz must be cleaned up, otherwise
	# Teamcity starts picking up artifacts from previous builds.
	#
	# We manually clean rather than having TeamCity always clean so that
	# builds are quicker.
	rm -rf dcos-release.config.yaml
	rm -rf artifacts/
	rm -f packages/*.active.json
	rm -f packages/bootstrap.latest
	rm -f packages/*.bootstrap.tar.xz
	rm -f CHANNEL_NAME
	rm -rf build/env
	rm -f dcos_generate_config*.sh
	rm -rf wheelhouse/
