# -*- coding: utf-8 -*-
# Copyright (C) Mesosphere, Inc. See LICENSE file for details.


import re
from setuptools import setup


requires = [
    'kazoo',
    'retrying'
]


version = re.search(
    '^__version__\s*=\s*"(.*)"',
    open('consensus/__init__.py').read(),
    re.M).group(1)

setup(
    name="zk-value-consensus",
    install_requires=requires,
    packages=["consensus"],
    entry_points={
        "console_scripts": ['zk-value-consensus = consensus.consensus:main']
    },
    version=version,
    description="Achieve consensus across multiple parties through ZooKeeper",
    author="Mesosphere, Inc.",
    author_email="help@dcos.io",
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
    ],
)
