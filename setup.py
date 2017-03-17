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
        'gen.build_deploy',
        'launch',
        'pkgpanda',
        'pkgpanda.build',
        'pkgpanda.http',
        'release',
        'release.storage',
        'ssh',
        'test_util'],
    install_requires=[
        'aiohttp==0.22.5',
        'analytics-python',
        'coloredlogs',
        'Flask',
        'flask-compress',
        # Pins taken from 'azure==2.0.0rc4'
        'msrest==0.4.0',
        'msrestazure==0.4.1',
        'azure-storage==0.32.0',
        'azure-mgmt-network==0.30.0rc4',
        'azure-mgmt-resource==0.30.0rc4',
        'boto3',
        'botocore',
        'coloredlogs',
        'docopt',
        'passlib',
        'py',
        'pyinstaller==3.2',
        'pytest',
        'pyyaml',
        'requests==2.10.0',
        'retrying',
        'keyring==9.1',  # FIXME: pin keyring to prevent dbus dep
        'teamcity-messages'],
    entry_points={
        'console_scripts': [
            'release=release:main',
            # Note: This test does not touch CCM, but this is here for backward compatible CI
            'ccm-deploy-test=test_util.test_aws_vpc:main',
            'test-aws-cf-deploy=test_util.test_aws_cf:main',
            'test-upgrade-vpc=test_util.test_upgrade_vpc:main',
            'test-azure-rm-deploy=test_util.test_azure:main',
            'pkgpanda=pkgpanda.cli:main',
            'mkpanda=pkgpanda.build.cli:main',
            'dcos_installer=dcos_installer.cli:main',
            'dcos-launch=launch.cli:main',
            'dcos-exhibitor-migrate-status=dcos_installer.exhibitor_migrate:status',
            'dcos-exhibitor-migrate-perform=dcos_installer.exhibitor_migrate:perform',
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
            'build_deploy/bash/dcos_generate_config.sh.in',
            'build_deploy/bash/Dockerfile.in',
            'build_deploy/bash/installer_internal_wrapper.in',
            'build_deploy/bash/dcos-launch.spec',
            'coreos-aws/cloud-config.yaml',
            'coreos/cloud-config.yaml'
        ] + get_advanced_templates(),
        'pkgpanda': [
            'docker/dcos-builder/Dockerfile'
        ],
        'launch': [
            'sample_configs/*.yaml',
            'dcos-launch.spec'
        ],
    },
    zip_safe=False
)
