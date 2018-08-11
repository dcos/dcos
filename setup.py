import platform
from pathlib import Path

from setuptools import setup


def get_advanced_templates():
    template_base = 'aws/templates/advanced/'
    template_names = ['advanced-master', 'advanced-priv-agent', 'advanced-pub-agent', 'infra', 'zen']

    return [template_base + name + '.json' for name in template_names]


# These files are expected source files to the dcos-builder docker.
# They need to match the contents of ./pkgpanda/docker/dcos-builder/*
# exactly otherwise the dcos-builder docker will have a different sha1
# checksum calculated during when the ./release script is run.
# That leads to cached packages hashes being different from what
# is cached in S3 and prevents us from building DC/OS locally.
if platform.system() == "Windows":
    expected_dcos_builder_files = [
        Path('docker.windows/dcos-builder/Dockerfile'),
        Path('docker.windows/dcos-builder/README.md'),
        Path('docker.windows/dcos-builder/setup-cmake.ps1'),
        Path('docker.windows/dcos-builder/setup-erlang.ps1'),
        Path('docker.windows/dcos-builder/setup-git.ps1'),
        Path('docker.windows/dcos-builder/setup-golang.ps1'),
        Path('docker.windows/dcos-builder/setup-make.ps1'),
        Path('docker.windows/dcos-builder/setup-patch.ps1')
    ]
    docker_directory = "docker.windows"
else:
    expected_dcos_builder_files = [
        Path('docker/dcos-builder/Dockerfile'),
        Path('docker/dcos-builder/README.md'),
    ]
    docker_directory = "docker"

dcos_builder_files = [
    f.relative_to(Path("./pkgpanda")) for f in Path("./pkgpanda").glob(docker_directory + '/**/*') if f.is_file()
]
if set(expected_dcos_builder_files) != set(dcos_builder_files):
    raise Exception('Expected ./pkgpanda/' + docker_directory + '/dcos-builder to contain {} but it had {}'.format(
        expected_dcos_builder_files, dcos_builder_files))


def get_extra_install_requires():
    if platform.system() == "Windows":
        return [
            'pywin32-ctypes',
            'colorama'
        ]
    else:
        return []


setup(
    name='dcos_image',
    version='0.1',
    description='DC/OS cluster configuration, assembly, and maintenance code',
    url='https://dcos.io',
    author='Mesosphere, Inc.',
    author_email='help@dcos.io',
    license='apache2',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
    ],
    packages=[
        'dcos_installer',
        'gen',
        'gen.build_deploy',
        'pkgpanda',
        'pkgpanda.build',
        'pkgpanda.http',
        'release',
        'release.storage',
        'ssh'],
    install_requires=[
        # DCOS-21656 - `botocore`` requires less than 2.7.0 while
        # `analytics-python` package installs 2.7.0 version
        'python-dateutil>=2.1,<2.7.0',
        'aiohttp==0.22.5',
        'analytics-python',
        'coloredlogs',
        'Flask',
        'flask-compress',
        'urllib3==1.22',
        'chardet',
        'PyJWT',
        # Pins taken from 'azure==2.0.0rc4'
        'msrest==0.4.17',
        'msrestazure==0.4.15',
        'azure-common==1.1.4',
        'azure-storage==0.32.0',
        'azure-mgmt-network==0.30.0rc4',
        'azure-mgmt-resource==0.30.0rc4',
        'botocore',
        'boto3',
        'checksumdir',
        'coloredlogs',
        'docopt',
        'passlib',
        'py',
        'pytest',
        'pyyaml',
        'requests==2.18.4',
        'retrying',
        'schema',
        'keyring==9.1',  # FIXME: pin keyring to prevent dbus dep
        'teamcity-messages'
    ] + get_extra_install_requires(),
    entry_points={
        'console_scripts': [
            'release=release:main',
            'pkgpanda=pkgpanda.cli:main',
            'mkpanda=pkgpanda.build.cli:main',
            'dcos_installer=dcos_installer.cli:main',
        ],
    },
    package_data={
        'gen': [
            'ip-detect/aws.ps1',
            'ip-detect/aws.sh',
            'ip-detect/aws6.ps1',
            'ip-detect/aws6.sh',
            'ip-detect/aws_public.ps1',
            'ip-detect/aws_public.sh',
            'ip-detect/azure.sh',
            'ip-detect/azure.ps1',
            'ip-detect/azure6.sh',
            'ip-detect/azure6.ps1',
            'ip-detect/vagrant.sh',
            'ip-detect/vagrant6.sh',
            'fault-domain-detect/cloud.sh',
            'fault-domain-detect/cloud.ps1',
            'fault-domain-detect/aws.sh',
            'fault-domain-detect/azure.sh',
            'cloud-config.yaml',
            'cloud-config-windows.yaml',
            'dcos-config.yaml',
            'dcos-config-windows.yaml',
            'dcos-metadata.yaml',
            'dcos-services.yaml',
            'dcos-services-windows.yaml',
            'aws/dcos-config.yaml',
            'aws/templates/aws.html',
            'aws/templates/cloudformation.json',
            'azure/cloud-config.yaml',
            'azure/cloud-config-windows.yaml',
            'azure/azuredeploy-parameters.json',
            'azure/templates/acs.json',
            'azure/templates/azure.html',
            'azure/templates/azuredeploy.json',
            'build_deploy/bash/dcos_generate_config.sh.in',
            'build_deploy/bash/dcos_generate_config.ps1.in',
            'build_deploy/bash/Dockerfile.in',
            'build_deploy/bash/Dockerfile.windows.in',
            'build_deploy/bash/installer_internal_wrapper.in',
            'build_deploy/bash/installer_internal_wrapper.ps1.in',
            'build_deploy/bash/dcos-launch.spec',
            'coreos-aws/cloud-config.yaml',
            'coreos/cloud-config.yaml'
        ] + get_advanced_templates(),
        'pkgpanda': [str(f) for f in expected_dcos_builder_files],
    },
    zip_safe=False
)
