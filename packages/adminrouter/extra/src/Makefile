.DEFAULT_GOAL := help
SHELL := /bin/bash

DEV_PATH := /usr/local/src

DCOSAR_AR_LOCAL_PATH := $(CURDIR)
DCOSAR_AR_CTR_MOUNT := /usr/local/adminrouter/nginx/conf/

BRIDGE_DEVNAME := $(shell docker network inspect -f '{{ index .Options "com.docker.network.bridge.name" }}' bridge | awk 'NF')
BRIDGE_IP := $(shell docker run --net=host --rm alpine ifconfig $(BRIDGE_DEVNAME) | grep 'inet addr:' | cut -d: -f2 | cut -d' ' -f1)

# FIXME: some problems with dns queries timing out, use hosts caching dns as a
# workaround for now
# DNS_DOCKER_OPTS := --dns=8.8.8.8 --dns=8.8.4.4
DNS_DOCKER_OPTS := --dns=$(BRIDGE_IP) --dns=8.8.8.8 --dns=8.8.4.4
DEVKIT_BASE_DOCKER_OPTS := --name adminrouter-devkit \
	$(DNS_DOCKER_OPTS) \
	-e NUM_CORES=2 \
	-e PYTHONDONTWRITEBYTECODE=true
DEVKIT_DOCKER_OPTS := $(DEVKIT_BASE_DOCKER_OPTS) \
	-v $(DCOSAR_AR_LOCAL_PATH):$(DCOSAR_AR_CTR_MOUNT)

.PHONY: clean-devkit-container
clean-devkit-container:
	-docker rm -vf adminrouter-devkit > /dev/null 2>&1

.PHONY: clean-containers
clean-containers: clean-devkit-container

.PHONY: clean
clean:
	@echo "+ Cleaning up..."
	-sudo find . -type f -name '*.pyc' -delete

.PHONY: devkit
devkit:
	if $$(docker images | grep mesosphere/adminrouter-devkit | grep -q full); then \
		echo "+ Devkit image already build"; \
	else \
		echo "+ Building devkit image"; \
		docker build \
			--rm --force-rm \
			-t mesosphere/adminrouter-devkit:noresty \
			-f ../../docker/Dockerfile \
				../../docker/ && \
		docker run \
			$(DEVKIT_BASE_DOCKER_OPTS) \
			mesosphere/adminrouter-devkit:noresty \
				/bin/bash -c "\$$OPENRESTY_COMPILE_SCRIPT" && \
		docker commit $$(docker ps -a -q -f name=adminrouter-devkit) \
			mesosphere/adminrouter-devkit:full && \
		docker rm adminrouter-devkit && \
		docker rmi -f mesosphere/adminrouter-devkit:noresty; \
	fi

.PHONY: update-devkit
update-devkit: clean-devkit-container
	-docker rm adminrouter-devkit
	docker build \
		--rm --force-rm \
		-t mesosphere/adminrouter-devkit:noresty \
		-f ../../docker/Dockerfile \
			../../docker/
	docker run \
		$(DEVKIT_BASE_DOCKER_OPTS) \
		mesosphere/adminrouter-devkit:noresty \
			/bin/bash -c "\$$OPENRESTY_COMPILE_SCRIPT" && \
	docker commit $$(docker ps -a -q -f name=adminrouter-devkit) \
		mesosphere/adminrouter-devkit:full
	docker rm adminrouter-devkit
	docker rmi -f mesosphere/adminrouter-devkit:noresty

.PHONY: shell
shell: clean-devkit-container devkit
	docker run --rm -it \
		$(DEVKIT_DOCKER_OPTS) \
		--privileged \
		mesosphere/adminrouter-devkit:full /bin/bash

.PHONY: test
test: clean-devkit-container devkit
	docker run \
		$(DEVKIT_DOCKER_OPTS) \
		--privileged \
		mesosphere/adminrouter-devkit:full /bin/bash -x -c " \
 			py.test \
 		"

.PHONY: flake8
flake8: clean-devkit-container devkit
	#FIXME - split it into two targets
	docker run \
		$(DEVKIT_DOCKER_OPTS) \
		mesosphere/adminrouter-devkit:full /bin/bash -x -c " \
			flake8 -v \
 		"

.PHONY: help
help:
	@echo "Please see README.md file."
