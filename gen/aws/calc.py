import pkg_resources

import yaml


def get_ip_detect(name):
    return yaml.dump(pkg_resources.resource_string('gen', 'ip-detect/{}.sh'.format(name)).decode())


def calculate_ip_detect_public_contents(aws_masters_have_public_ip):
    return get_ip_detect({'true': 'aws_public', 'false': 'aws'}[aws_masters_have_public_ip])


entry = {
    'default': {
        'resolvers': '["169.254.169.253"]',
        'num_private_slaves': '5',
        'num_public_slaves': '1',
        'os_type': '',
        'aws_masters_have_public_ip': 'true',
        'enable_docker_gc': 'true'
    },
    'must': {
        'aws_region': '{ "Ref" : "AWS::Region" }',
        'ip_detect_contents': get_ip_detect('aws'),
        'ip_detect_public_contents': calculate_ip_detect_public_contents,
        'exhibitor_explicit_keys': 'false',
        'cluster_name': '{ "Ref" : "AWS::StackName" }',
        'master_discovery': 'master_http_loadbalancer',
        # The cloud_config template variables pertaining to "cloudformation.json"
        'master_cloud_config': '{{ master_cloud_config }}',
        'agent_private_cloud_config': '{{ slave_cloud_config }}',
        'agent_public_cloud_config': '{{ slave_public_cloud_config }}',
        # template variable for the generating advanced template cloud configs
        'cloud_config': '{{ cloud_config }}',
        'oauth_available': 'true',
        'oauth_enabled': '{ "Ref" : "OAuthEnabled" }',
        'rexray_config_preset': 'aws'
    }
}
