from setuptools import find_packages, setup

setup(
    name='dcos_installer',
    description='DC/OS Installer Backend',
    version='0.1',
    author='Mesosphere, Inc.',
    author_email='help@dcos.io',
    packages=['dcos_installer'] + find_packages(),
    license='apache2',
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
    ],
    install_requires=[
        'aiohttp==0.22.5',
        'coloredlogs',
        'passlib',
        'analytics-python',
        'pyyaml'],
    entry_points={
        'console_scripts': [
            'dcos_installer = dcos_installer.cli:main']
    },
    include_package_data=True,
    zip_safe=False
)
