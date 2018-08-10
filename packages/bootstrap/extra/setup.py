import platform

from setuptools import setup


requires = [
    'kazoo',
    'requests',
    'portalocker'
]

if platform.system() == "Windows":
    requires += [
        'pywin32',
        'pypiwin32'
    ]


setup(
    name="dcos-internal-utils",
    install_requires=requires,
    packages=[
        'dcos_internal_utils',
    ],
    version='0.0.1',
    description='DC/OS Internal Utilities Library',
    author='Mesosphere, Inc.',
    author_email='support@mesosphere.io',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6'],
    entry_points={
        'console_scripts': [
            'bootstrap=dcos_internal_utils.cli:main'
        ]
    })
