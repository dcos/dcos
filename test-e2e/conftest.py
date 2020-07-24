import logging

# Hack to exclude test-e2e/conftest.py from the top-level tox config py35-unittests.
# https://stackoverflow.com/a/37493203
pytest_plugins = ['e2e_module']
# Actual content of conftest.py can be found in e2e_module.py.

# Configures logging level to DEBUG
logging.basicConfig(level=logging.DEBUG)
