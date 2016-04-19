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
        'aiohttp==0.20.0',
        'aiohttp_jinja2',
        'coloredlogs',
        'passlib',
        'pyyaml'],
    tests_require=[
        'pytest==2.9.0',
        'pytest-mock==0.11.0',
        'webtest==2.0.20',
        'webtest-aiohttp==1.0.0'],
    test_suite='pytest',
    entry_points={
        'console_scripts': [
            'dcos_installer = dcos_installer.entrypoint:main']
    },
    include_package_data=True,
    zip_safe=False
)
