"""
flake8 plugin for dcos code base.

This is flake8 extension that provides custom code quality checks for DCOS project. The syntax rules can be added as
Regex in check_rules.py module. New plugins can be introduced by following the flake8 extension guide
(http://flake8.pycqa.org/en/latest/plugin-development/index.html). And they will automatically be run as part of the
syntax-check.
"""
from __version__ import PLUGIN_NAME, PLUGIN_VERSION

from setuptools import setup

setup(
    name=PLUGIN_NAME,
    version=PLUGIN_VERSION,
    description='flake8 plugin for custom dcos checks',
    py_modules=["check_rules", "checker"],
    install_requires=[
        'pycodestyle',
        'flake8',
        'flake8-import-order==0.9.2',
        'pep8-naming'
    ],
    entry_points={
        'flake8.extension': [
            '{} = checker:check'.format(PLUGIN_NAME),
        ],
    }
)
