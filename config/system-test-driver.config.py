#!/usr/bin/env python
import json
import os
import sys
import glob
import urllib.parse

#
# This is a configuration script to the system-test-driver that runs the
# system integration tests against a newly provisioned DC/OS Cluster.
#

# List of packages with dcos system tests\
TESTABLE_PACKAGES = ['dcos-ui']
PACKAGES_DIRECTORY = '../packages/'


def compose_suite_uri_git(build_info_source):
    git_uri = build_info_source['git']
    git_cred = ''

    if 'GIT_USERNAME' in os.environ and 'GIT_PASSWORD' in os.environ:
        git_cred = '%s:%s@' % (
            os.environ['GIT_USERNAME'], os.environ['GIT_PASSWORD'])

    if git_uri.startswith('git@'):
        git_uri = 'https://%s' % git_uri[4:].replace(':', '/')

    git_uri_tuple = urllib.parse.urlparse(git_uri)

    return 'git:%s://%s%s%s#%s' % (
        git_uri_tuple.scheme,
        git_cred,
        git_uri_tuple.netloc,
        git_uri_tuple.path,
        build_info_source['ref']
    )


def compose_suite_uri(accumulator, source):
    if source['kind'] == 'git':
        accumulator.append(compose_suite_uri_git(source))
    return accumulator


def parse_buildinfo_sources(build_info, source_callback):
    accumulator = []

    if 'sources' in build_info:
        for source in build_info['sources']:
            accumulator = source_callback(
                accumulator,
                build_info['sources'][source]
            )
    else:
        accumulator = source_callback(accumulator, build_info['single_source'])

    return accumulator


def compose_suite_paths_for_packages(packages_dir, packages):
    suites = []
    for package in packages:
        for filename in glob.glob(
                '%s/%s/*buildinfo.json' % (packages_dir, package)):
            with open(filename, 'r') as json_file:
                build_info = json.load(json_file)
                suites += parse_buildinfo_sources(build_info, compose_suite_uri)

    return suites


def compose_cluster_name(ccm_channel):
    return ccm_channel.replace("/", "-")[:40]


if __name__ == '__main__':
    # Ensure CCM_AUTH_TOKEN is specified
    if 'CCM_AUTH_TOKEN' not in os.environ:
        print('Error: Please specify the CCM_AUTH_TOKEN environment variable')
        sys.exit()

    # Print system test driver config
    print(json.dumps({
        'config': {
            'name': 'dcos-system-test'
        },
        'criteria': [],
        'suites': compose_suite_paths_for_packages(
            PACKAGES_DIRECTORY,
            TESTABLE_PACKAGES
        ),
        'targets': [
            {
                'name': compose_cluster_name(os.environ.get(
                    'CCM_CHANNEL',
                    'testing/master'
                )),
                'title': 'DC/OS Cluster',
                'features': [],
                'config': {
                    'template':
                        os.environ.get(
                            'CCM_TEMPLATE',
                            'single-master.cloudformation.json'
                        ),
                    'channel':
                        os.environ.get(
                            'CCM_CHANNEL',
                            'testing/master'
                        ),
                },
                'type': 'ccm',
                'scripts': {
                    'auth': '../scripts/auth-open.py',
                }
            }
        ],
        'secrets': {
            'ccm_token': os.environ.get('CCM_AUTH_TOKEN')
        }
    }))
