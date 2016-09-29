from setuptools import setup

config = {
    'name': 'dcos-history',
    'version': '0.1.0',
    'description': 'Buffers the state of the mesos leading master state',
    'author': 'Mesosphere, Inc.',
    'author_email': 'help@dcos.io',
    'maintainer': 'DC/OS Community',
    'maintainer_email': 'help@dcos.io',
    'url': 'https://dcos.io',
    'packages': [
        'history'
    ],
    'entry_points': {
        'console_scripts': [
            'dcos-history = history.server:start'
        ]
    },
    'install_requires': [
        'aiohttp==0.22.5',
        'requests']
}

setup(**config)
