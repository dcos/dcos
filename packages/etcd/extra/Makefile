.DEFAULT_GOAL := lint
SHELL:=/bin/bash

ZK_CONTAINER_NAME := etcd_discovery-zookeeper-test

.PHONY: yapf
yapf:
	yapf --diff --recursive ./etcd_discovery/*.py ./tests/*.py

.PHONY: fix-yapf
fix-yapf:
	yapf \
	    --in-place \
	    --recursive \
	    --style '{indent_dictionary_value:False}' \
	    ./etcd_discovery/*.py ./tests/*.py

.PHONY: mypy
mypy:
	mypy --config-file ./mypy.ini \
	    ./etcd_discovery/*.py

.PHONY: flake8
flake8:
	flake8 ./*.py \
	    ./etcd_discovery/*.py ./tests/*.py

.PHONY: pylint
pylint:
	pylint --rcfile=./pylintrc \
	    ./etcd_discovery/*.py

.PHONY: fix-autoflake
fix-autoflake:
	autoflake \
	    --in-place \
	    --recursive \
	    --remove-all-unused-imports \
	    --remove-unused-variables \
	    --expand-star-imports \
	    	./etcd_discovery/*.py ./tests/*.py

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

.PHONY: lint
lint: \
	flake8 \
	yapf \
	mypy

.PHONY: fix-lint
fix-lint: \
	fix-autoflake \
	fix-yapf \
	pylint
