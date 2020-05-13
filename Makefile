
.PHONY: tox
tox:
	rm -rf dcos-release.config.yaml
	cp config/dcos-release.config.yaml dcos-release.config.yaml
	pip install tox && tox

.PHONY: clean
clean:
	_scope_opened "cleanup"
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
	_scope_closed "cleanup"
