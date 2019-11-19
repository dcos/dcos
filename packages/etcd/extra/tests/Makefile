.DEFAULT_GOAL := default
SHELL:=/bin/bash

ZK_CONTAINER_NAME := etcd_discovery-zookeeper-test

.PHONY: start-zk
start-zk:
	@running_containers=$$(docker ps -f "name=$(ZK_CONTAINER_NAME)" -q | wc -l); \
	if (( $${running_containers} < 1 )); then \
		echo "Starting ZK container"; \
		docker run \
			--name $(ZK_CONTAINER_NAME) \
			-e PYTHONDONTWRITEBYTECODE=true \
			--restart always \
			-p 2181:2181 \
			-d zookeeper:3.5.5; \
	else \
		echo "ZK container is already running"; \
	fi

.PHONY: test
test:
	py.test -s ./

.PHONY: stop-zk
stop-zk:
	@-docker rm -f $(ZK_CONTAINER_NAME)

.PHONY: default
default: start-zk test stop-zk