
.PHONY: tox
tox:
	rm -rf dcos-release.config.yaml
	cp config/dcos-release.config.yaml dcos-release.config.yaml
	pip install tox && tox
