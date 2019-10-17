.PHONY: pylint
py-lint:
	make -C cockroach py-lint
	make -C dcos-integration-test py-lint
	make -C exhibitor py-lint

.PHONY: fix-py-lint
fix-py-lint:
	make -C cockroach fix-py-lint
	make -C dcos-integration-test fix-py-lint
	make -C exhibitor fix-py-lint

