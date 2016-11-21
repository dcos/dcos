from setuptools import setup


def get_advanced_templates():
    template_base = 'aws/templates/advanced/'
    template_names = ['advanced-master', 'advanced-priv-agent', 'advanced-pub-agent', 'infra', 'zen']

    return [template_base + name + '.json' for name in template_names]


setup(
    name='dcos_image',
    version='0.1',
    description='DC/OS cluster configuration, assembly, and launch, and maintenance code',
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
    packages=[
        'dcos_installer',
        'gen',
        'gen.aws',
        'gen.azure',
        'gen.installer',
        'pkgpanda',
        'pkgpanda.build',
        'pkgpanda.http',
        'release',
        'release.storage',
        'ssh',
        'test_util'],
    install_requires=[
        'aiohttp==0.22.5',
        'analytics-python==1.2.5',
        'coloredlogs==5.2',
        'Flask==0.11.1',
        'flask-compress==1.3.2',
        # Pins taken from 'azure==2.0.0rc4'
        'msrest==0.4.0',
        'msrestazure==0.4.1',
        'azure-storage==0.32.0',
        'azure-mgmt-network==0.30.0rc4',
        'azure-mgmt-resource==0.30.0rc4',
        'boto3==1.4.1',
        'botocore==1.4.74',
        'coloredlogs==5.2',
        'docopt==0.6.2',
        'passlib==1.6.5',
        'py==1.4.31',
        'pyinstaller==3.2',
        'pyyaml==3.12',
        'requests==2.10.0',
        'retrying==1.3.3',
        'keyring==9.1'],  # FIXME: pin keyring to prevent dbus dep
    entry_points={
        'console_scripts': [
            'release=release:main',
            # Note: This test does not touch CCM, but this is here for backward compatible CI
            'ccm-deploy-test=test_util.test_aws_vpc:main',
            'test-aws-cf-deploy=test_util.test_aws_cf:main',
            'test-upgrade-vpc=test_util.test_upgrade_vpc:main',
            'test-azure-rm-deploy=test_util.azure_test_driver:main',
            'pkgpanda=pkgpanda.cli:main',
            'mkpanda=pkgpanda.build.cli:main',
            'dcos_installer=dcos_installer.cli:main',
            'dcos-launch=test_util.launch:main',
        ],
    },
    package_data={
        'gen': [
            'ip-detect/aws.sh',
            'ip-detect/aws_public.sh',
            'ip-detect/azure.sh',
            'ip-detect/vagrant.sh',
            'cloud-config.yaml',
            'dcos-config.yaml',
            'dcos-metadata.yaml',
            'dcos-services.yaml',
            'aws/dcos-config.yaml',
            'aws/templates/aws.html',
            'aws/templates/cloudformation.json',
            'azure/cloud-config.yaml',
            'azure/azuredeploy-parameters.json',
            'azure/templates/acs.json',
            'azure/templates/azure.html',
            'azure/templates/azuredeploy.json',
            'installer/bash/dcos_generate_config.sh.in',
            'installer/bash/Dockerfile.in',
            'installer/bash/installer_internal_wrapper.in',
            'installer/bash/dcos-launch.spec',
            'coreos-aws/cloud-config.yaml',
            'coreos/cloud-config.yaml'
        ] + get_advanced_templates(),
        'pkgpanda': [
            'docker/dcos-builder/Dockerfile'
        ],
        'test_util': [
            'launch.py'
        ]
    },
    zip_safe=False
)
