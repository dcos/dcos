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
