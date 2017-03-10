from setuptools import setup


setup(
    name='dcos-launch',
    version='0.1',
    description='DC/OS cluster launch code',
    url='https://dcos.io',
    author='Mesosphere, Inc.',
    author_email='help@dcos.io',
    license='apache2',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
    ],
    packages=['launch'],
    install_requires=[
        # Pins taken from 'azure==2.0.0rc4'
        'msrest==0.4.0',
        'msrestazure==0.4.1',
        'azure-storage==0.32.0',
        'azure-mgmt-network==0.30.0rc4',
        'azure-mgmt-resource==0.30.0rc4',
        'boto3',
        'botocore',
        'docopt',
        'pyinstaller==3.2',
        'pyyaml'],
    entry_points={
        'console_scripts': [
            'dcos-launch=launch.cli:main',
        ],
    },
    package_data={
        'launch': [
            'sample_configs/*.yaml',
            'dcos-launch.spec'
        ],
    },
    zip_safe=False
)
