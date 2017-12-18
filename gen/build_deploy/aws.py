"""AWS Image Creation, Management, Testing"""

import json
import logging
from copy import deepcopy
from typing import Tuple

import botocore.exceptions
import yaml
from pkg_resources import resource_string
from retrying import retry

import gen
import gen.build_deploy.util as util
import pkgpanda.util
import release
import release.storage
from gen.internals import Late, Source
from pkgpanda.util import logger, split_by_token


def get_ip_detect(name):
    return yaml.dump(resource_string('gen', 'ip-detect/{}.sh'.format(name)).decode())


def calculate_ip_detect_public_contents(aws_masters_have_public_ip):
    return get_ip_detect({'true': 'aws_public', 'false': 'aws'}[aws_masters_have_public_ip])


def validate_provider(provider):
    assert provider == 'aws'


aws_base_source = Source(entry={
    'validate': [
        validate_provider
    ],
    'default': {
        'platform': 'aws',
        'resolvers': '["169.254.169.253"]',
        'num_private_slaves': '5',
        'num_public_slaves': '1',
        'os_type': '',
        'aws_masters_have_public_ip': 'true',
        'enable_docker_gc': 'true'
    },
    'must': {
        'aws_region': Late('{ "Ref" : "AWS::Region" }'),
        'aws_stack_id': Late('{ "Ref" : "AWS::StackId" }'),
        'aws_stack_name': Late('{ "Ref" : "AWS::StackName" }'),
        'ip_detect_contents': get_ip_detect('aws'),
        'ip_detect_public_contents': calculate_ip_detect_public_contents,
        'exhibitor_explicit_keys': 'false',
        'cluster_name': Late('{ "Ref" : "AWS::StackName" }'),
        'master_discovery': 'master_http_loadbalancer',
        # DRY the cluster packages list in CF templates.
        # This late expression isn't a Late because cluster-packages.json must go into cloud config, not the late
        # package. The variable referenced here is stored behind two unnecessary keys because of CF template syntax
        # requirements. See
        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/mappings-section-structure.html.
        # TODO(branden): Make this unnecessary by turning cluster-packages.json into a build artifact. See
        # https://mesosphere.atlassian.net/browse/DCOS-13824.
        'cluster_packages_json': '{ "Fn::FindInMap" : [ "ClusterPackagesJson", "default", "default" ] }',
        'cluster_packages_json_var': lambda cluster_packages: json.dumps(cluster_packages),
        # The cloud_config template variables pertaining to "cloudformation.json"
        'master_cloud_config': '{{ master_cloud_config }}',
        'agent_private_cloud_config': '{{ slave_cloud_config }}',
        'agent_public_cloud_config': '{{ slave_public_cloud_config }}',
        # template variable for the generating advanced template cloud configs
        'cloud_config': '{{ cloud_config }}',
        'rexray_config_preset': 'aws'
    },
    'conditional': {
        'oauth_available': {
            'true': {
                'must': {
                    'oauth_enabled': Late('{ "Ref" : "OAuthEnabled" }'),
                    'adminrouter_auth_enabled': Late('{ "Ref" : "OAuthEnabled" }'),
                }
            },
            'false': {},
        }
    }
})


aws_region_names = [
    {
        'name': 'US West (N. California)',
        'id': 'us-west-1'
    },
    {
        'name': 'US West (Oregon)',
        'id': 'us-west-2'
    },
    {
        'name': 'US East (N. Virginia)',
        'id': 'us-east-1'
    },
    {
        'name': 'South America (Sao Paulo)',
        'id': 'sa-east-1'
    },
    {
        'name': 'EU (Ireland)',
        'id': 'eu-west-1'
    },
    {
        'name': 'EU (Frankfurt)',
        'id': 'eu-central-1'
    },
    {
        'name': 'Asia Pacific (Tokyo)',
        'id': 'ap-northeast-1'
    },
    {
        'name': 'Asia Pacific (Singapore)',
        'id': 'ap-southeast-1'
    },
    {
        'name': 'Asia Pacific (Sydney)',
        'id': 'ap-southeast-2'
    }]


region_to_ami_map = {
    'ap-northeast-1': {
        'coreos': 'ami-93f2baf4',
        'stable': 'ami-93f2baf4',
        'el7': 'ami-e21fd884',
        'natami': 'ami-55c29e54'
    },
    'ap-southeast-1': {
        'coreos': 'ami-aacc7dc9',
        'stable': 'ami-aacc7dc9',
        'el7': 'ami-3b8ee058',
        'natami': 'ami-b082dae2'
    },
    'ap-southeast-2': {
        'coreos': 'ami-9db0b0fe',
        'stable': 'ami-9db0b0fe',
        'el7': 'ami-c2e501a0',
        'natami': 'ami-996402a3'
    },
    'eu-central-1': {
        'coreos': 'ami-903df7ff',
        'stable': 'ami-903df7ff',
        'el7': 'ami-868531e9',
        'natami': 'ami-204c7a3d'
    },
    'eu-west-1': {
        'coreos': 'ami-abcde0cd',
        'stable': 'ami-abcde0cd',
        'el7': 'ami-5f03c426',
        'natami': 'ami-3760b040'
    },
    'sa-east-1': {
        'coreos': 'ami-c11573ad',
        'stable': 'ami-c11573ad',
        'el7': 'ami-5d2f5d31',
        'natami': 'ami-b972dba4'
    },
    'us-east-1': {
        'coreos': 'ami-1ad0000c',
        'stable': 'ami-1ad0000c',
        'el7': 'ami-abb1a2d0',
        'natami': 'ami-4c9e4b24'
    },
    'us-gov-west-1': {
        'coreos': 'ami-e441fb85',
        'stable': 'ami-e441fb85',
        'el7': 'ami-e58c0f84',
        'natami': ''
    },
    'us-west-1': {
        'coreos': 'ami-b31d43d3',
        'stable': 'ami-b31d43d3',
        'el7': 'ami-f6427596',
        'natami': 'ami-2b2b296e'
    },
    'us-west-2': {
        'coreos': 'ami-444dcd24',
        'stable': 'ami-444dcd24',
        'el7': 'ami-6eed1a16',
        'natami': 'ami-bb69128b'
    }
}


late_services = """- name: dcos-cfn-signal.service
  command: start
  no_block: true
  content: |
    [Unit]
    Description=AWS Setup: Signal CloudFormation Success
    ConditionPathExists=!/var/lib/dcos-cfn-signal
    [Service]
    Type=simple
    Restart=on-failure
    StartLimitInterval=0
    RestartSec=15s
    EnvironmentFile=/opt/mesosphere/environment
    EnvironmentFile=/opt/mesosphere/etc/cfn_signal_metadata
    Environment="AWS_CFN_SIGNAL_THIS_RESOURCE={{ report_name }}"
    ExecStartPre=/bin/ping -c1 leader.mesos
    ExecStartPre=/opt/mesosphere/bin/cfn-signal
    ExecStart=/usr/bin/touch /var/lib/dcos-cfn-signal"""

cf_instance_groups = {
    'master': {
        'report_name': 'MasterServerGroup',
        'roles': ['master', 'aws_master']
    },
    'slave': {
        'report_name': 'SlaveServerGroup',
        'roles': ['slave']
    },
    'slave_public': {
        'report_name': 'PublicSlaveServerGroup',
        'roles': ['slave_public']
    }
}

# TODO(cmaloney): this and cf_instance_groups should be the _same_ dictionary
# this just being accessing the report-name key.
aws_advanced_report_names = {
    'master': 'MasterServerGroup',
    'pub-agent': 'PublicAgentServerGroup',
    'priv-agent': 'PrivateAgentServerGroup'
}

groups = {
    'master': (
        'master', Source(entry={'must': {
            's3_bucket': Late('{ "Ref" : "ExhibitorS3Bucket" }'),
            's3_prefix': Late('{ "Ref" : "AWS::StackName" }'),
            'exhibitor_storage_backend': 'aws_s3',
            'master_role': Late('{ "Ref" : "MasterRole" }'),
            'agent_role': '',
            'exhibitor_address': Late('{ "Fn::GetAtt" : [ "InternalMasterLoadBalancer", "DNSName" ] }'),
            'has_master_external_loadbalancer': 'true',
            'master_external_loadbalancer': Late('{ "Fn::GetAtt" : [ "ElasticLoadBalancer", "DNSName" ] }'),
        }})),
    'pub-agent': (
        'slave_public', Source(entry={'must': {
            'master_role': '',
            'agent_role': Late('{ "Ref" : "PublicAgentRole" }'),
            'exhibitor_storage_backend': 'agent_only_group_no_exhibitor',
            'exhibitor_address': Late('{ "Ref" : "InternalMasterLoadBalancerDnsName" }'),
        }})),
    'priv-agent': (
        'slave', Source(entry={'must': {
            'master_role': '',
            'agent_role': Late('{ "Ref" : "PrivateAgentRole" }'),
            'exhibitor_storage_backend': 'agent_only_group_no_exhibitor',
            'exhibitor_address': Late('{ "Ref" : "InternalMasterLoadBalancerDnsName" }'),
        }}))
}


def get_test_session(config=None):
    if config is None:
        assert release._config is not None
        # TODO(cmaloney): HACK. Stashing and pulling the config from release/__init__.py
        # is definitely not the right way to do this.

        if 'testing' not in release._config:
            raise RuntimeError("No testing section in configuration")

        if 'aws' not in release._config['testing']:
            raise RuntimeError("No testing.aws section in configuration")

        config = release._config['testing']['aws']

    # TODO(cmaloney): get_session shouldn't live in release.storage
    return release.call_matching_arguments(release.storage.aws.get_session, config, True)


def gen_ami_mapping(mappings):
    # create new dict with required mappings
    # all will have region by default
    final = {}
    for region, amis in region_to_ami_map.items():
        final[region] = dict()
        for map_entry in mappings:
            final_key = 'default' if map_entry == 'natami' else map_entry
            final[region][final_key] = amis[map_entry]

    return json.dumps(final, indent=4, sort_keys=True)


def transform(line):

    def _jsonify_literals(parts):
        for part, is_ref in parts:
            if is_ref:
                yield part
            else:
                yield json.dumps(part)

    return ', '.join(_jsonify_literals(split_by_token('{ ', ' }', line))) + ', "\\n",\n'


def render_cloudformation_transform(cf_template, transform_func=lambda x: x, **kwds):
    # TODO(cmaloney): There has to be a cleaner way to do this transformation.
    # For now just moved from cloud_config_cf.py
    # TODO(cmaloney): Move with the logic that does this same thing in Azure

    template_str = gen.template.parse_str(cf_template).render(
        {k: transform_func(v) for k, v in kwds.items()}
    )

    template_json = json.loads(template_str)

    template_json['Metadata']['DcosImageCommit'] = util.dcos_image_commit
    template_json['Metadata']['TemplateGenerationDate'] = util.template_generation_date

    return json.dumps(template_json)


def render_cloudformation(cf_template, **kwds):
    def transform_lines(text):
        return ''.join(map(transform, text.splitlines())).rstrip(',\n')

    return render_cloudformation_transform(cf_template, transform_func=transform_lines, **kwds)


@retry(stop_max_attempt_number=5, wait_exponential_multiplier=1000)
def validate_cf(template_body):
    try:
        session = get_test_session()
    except Exception as ex:
        logging.warning("Skipping  AWS CloudFormation validation because couldn't get a test session: {}".format(ex))
        return
    client = session.client('cloudformation')
    try:
        client.validate_template(TemplateBody=template_body)
    except botocore.exceptions.ClientError as ex:
        print(json.dumps(json.loads(template_body), indent=4))
        raise ex


def _as_cf_artifact(filename, cloudformation):
    return {
        'channel_path': 'cloudformation/{}'.format(filename),
        'local_content': cloudformation,
        'content_type': 'application/json; charset=utf-8'
    }


def _as_artifact_and_pkg(variant_prefix, filename, bundle: Tuple):
    cloudformation, results = bundle
    yield _as_cf_artifact("{}{}".format(variant_prefix, filename), cloudformation)
    yield {'packages': results.config_package_ids}
    if results.late_package_id:
        yield {'packages': [results.late_package_id]}


def gen_supporting_template():
    for template_key in ['infra.json']:
        cf_template = 'aws/templates/advanced/{}'.format(template_key)
        cloudformation = render_cloudformation_transform(resource_string("gen", cf_template).decode(),
                                                         nat_ami_mapping=gen_ami_mapping({'natami'}))

        print("Validating CloudFormation: {}".format(cf_template))
        validate_cf(cloudformation)

        yield _as_cf_artifact(
            template_key,
            cloudformation)


def make_advanced_bundle(variant_args, extra_sources, template_name, cc_params):
    extra_templates = [
        'aws/dcos-config.yaml',
        'aws/templates/advanced/{}'.format(template_name)
    ]
    if cc_params['os_type'] == 'coreos':
        extra_templates += ['coreos-aws/cloud-config.yaml', 'coreos/cloud-config.yaml']
        cloud_init_implementation = 'coreos'
    elif cc_params['os_type'] == 'el7':
        cloud_init_implementation = 'canonical'
    else:
        raise RuntimeError('Unsupported os_type: {}'.format(cc_params['os_type']))

    results = gen.generate(
        arguments=variant_args,
        extra_templates=extra_templates,
        extra_sources=extra_sources + [aws_base_source],
        # TODO(cmaloney): Merge this with dcos_installer/backend.py::get_aws_advanced_target()
        extra_targets=[gen.internals.Target(variables={'cloudformation_s3_url_full'})])

    cloud_config = results.templates['cloud-config.yaml']

    # Add general services
    cloud_config = results.utils.add_services(cloud_config, cloud_init_implementation)

    cc_variant = deepcopy(cloud_config)
    cc_variant = results.utils.add_units(
        cc_variant,
        yaml.safe_load(gen.template.parse_str(late_services).render(cc_params)),
        cloud_init_implementation)

    # Add roles
    cc_variant = results.utils.add_roles(cc_variant, cc_params['roles'] + ['aws'])

    # NOTE: If this gets printed in string stylerather than '|' the AWS
    # parameters which need to be split out for the cloudformation to
    # interpret end up all escaped and undoing it would be hard.
    variant_cloudconfig = results.utils.render_cloudconfig(cc_variant)

    # Render the cloudformation
    cloudformation = render_cloudformation(
        results.templates[template_name],
        cloud_config=variant_cloudconfig)
    print("Validating CloudFormation: {}".format(template_name))
    validate_cf(cloudformation)

    return (cloudformation, results)


def gen_advanced_template(arguments, variant_prefix, reproducible_artifact_path, os_type):
    for node_type in ['master', 'priv-agent', 'pub-agent']:
        # TODO(cmaloney): This forcibly overwriting arguments might overwrite a user set argument
        # without noticing (such as exhibitor_storage_backend)
        node_template_id, node_source = groups[node_type]
        local_source = Source()
        local_source.add_must('os_type', os_type)
        local_source.add_must('region_to_ami_mapping', gen_ami_mapping({"coreos", "el7"}))
        params = deepcopy(cf_instance_groups[node_template_id])
        params['report_name'] = aws_advanced_report_names[node_type]
        params['os_type'] = os_type
        params['node_type'] = node_type
        template_key = 'advanced-{}'.format(node_type)
        template_name = template_key + '.json'

        def _as_artifact(filename, bundle):
            yield from _as_artifact_and_pkg(variant_prefix, filename, bundle)

        if node_type == 'master':
            for num_masters in [1, 3, 5, 7]:
                master_tk = '{}-{}-{}'.format(os_type, template_key, num_masters)
                print('Building {} {} for num_masters = {}'.format(os_type, node_type, num_masters))
                num_masters_source = Source()
                num_masters_source.add_must('num_masters', str(num_masters))
                bundle = make_advanced_bundle(arguments,
                                              [node_source, local_source, num_masters_source],
                                              template_name,
                                              params)
                yield from _as_artifact('{}.json'.format(master_tk), bundle)

                # Zen template corresponding to this number of masters
                yield _as_cf_artifact(
                    '{}{}-zen-{}.json'.format(variant_prefix, os_type, num_masters),
                    render_cloudformation_transform(
                        resource_string("gen", "aws/templates/advanced/zen.json").decode(),
                        variant_prefix=variant_prefix,
                        reproducible_artifact_path=reproducible_artifact_path,
                        **bundle[1].arguments))
        else:
            local_source.add_must('num_masters', '1')
            local_source.add_must('nat_ami_mapping', gen_ami_mapping({"natami"}))
            bundle = make_advanced_bundle(arguments,
                                          [node_source, local_source],
                                          template_name,
                                          params)
            yield from _as_artifact('{}-{}'.format(os_type, template_name), bundle)


aws_simple_source = Source({
    'must': {
        'exhibitor_address': Late('{ "Fn::GetAtt" : [ "InternalMasterLoadBalancer", "DNSName" ] }'),
        's3_bucket': Late('{ "Ref" : "ExhibitorS3Bucket" }'),
        'exhibitor_storage_backend': 'aws_s3',
        'master_role': Late('{ "Ref" : "MasterRole" }'),
        'agent_role': Late('{ "Ref" : "SlaveRole" }'),
        's3_prefix': Late('{ "Ref" : "AWS::StackName" }'),
        'region_to_ami_mapping': gen_ami_mapping({"stable"}),
        'nat_ami_mapping': gen_ami_mapping({"natami"}),
        'has_master_external_loadbalancer': 'true',
        'master_external_loadbalancer': Late('{ "Fn::GetAtt" : [ "ElasticLoadBalancer", "DNSName" ] }'),
    }
})


def gen_simple_template(variant_prefix, filename, arguments, extra_source):
    results = gen.generate(
        arguments=arguments,
        extra_templates=[
            'aws/templates/cloudformation.json',
            'aws/dcos-config.yaml',
            'coreos-aws/cloud-config.yaml',
            'coreos/cloud-config.yaml'],
        extra_sources=[aws_base_source, aws_simple_source, extra_source])

    cloud_config = results.templates['cloud-config.yaml']

    # Add general services
    cloud_config = results.utils.add_services(cloud_config, 'coreos')

    # Specialize for master, slave, slave_public
    variant_cloudconfig = {}
    for variant, params in cf_instance_groups.items():
        cc_variant = deepcopy(cloud_config)

        # Specialize the dcos-cfn-signal service
        cc_variant = results.utils.add_units(
            cc_variant,
            yaml.safe_load(gen.template.parse_str(late_services).render(params)))

        # Add roles
        cc_variant = results.utils.add_roles(cc_variant, params['roles'] + ['aws'])

        # NOTE: If this gets printed in string stylerather than '|' the AWS
        # parameters which need to be split out for the cloudformation to
        # interpret end up all escaped and undoing it would be hard.
        variant_cloudconfig[variant] = results.utils.render_cloudconfig(cc_variant)

    # Render the cloudformation
    cloudformation = render_cloudformation(
        results.templates['cloudformation.json'],
        master_cloud_config=variant_cloudconfig['master'],
        slave_cloud_config=variant_cloudconfig['slave'],
        slave_public_cloud_config=variant_cloudconfig['slave_public'])

    with logger.scope("Validating CloudFormation"):
        validate_cf(cloudformation)

    yield from _as_artifact_and_pkg(variant_prefix, filename, (cloudformation, results))


button_template = "<a href='https://console.aws.amazon.com/cloudformation/home?region={region_id}#/stacks/new?templateURL={cloudformation_full_s3_url}/{template_name}.cloudformation.json'><img src='https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png' alt='Launch stack button'></a>"  # noqa
region_line_template = "<tr><td>{region_name}</td><td>{region_id}</td><td>{single_master_button}</td><td>{multi_master_button}</td></tr>"  # noqa


def gen_buttons(build_name, reproducible_artifact_path, tag, commit, variant_arguments):
    # Generate the button page.
    # TODO(cmaloney): Switch to package_resources
    variant_list = list(sorted(pkgpanda.util.variant_prefix(x) for x in variant_arguments.keys()))
    regular_buttons = list()

    for region in aws_region_names:
        def get_button(template_name, s3_url):
            return button_template.format(
                region_id=region['id'],
                reproducible_artifact_path=reproducible_artifact_path,
                template_name=template_name,
                cloudformation_full_s3_url=s3_url)

        button_line = ""
        for variant, arguments in variant_arguments.items():
            variant_prefix = pkgpanda.util.variant_prefix(variant)
            s3_url = arguments['cloudformation_s3_url_full']
            button_line += region_line_template.format(
                region_name=region['name'],
                region_id=region['id'],
                single_master_button=get_button(variant_prefix + 'single-master', s3_url=s3_url),
                multi_master_button=get_button(variant_prefix + 'multi-master', s3_url=s3_url))

        regular_buttons.append(button_line)

    return gen.template.parse_resources('aws/templates/aws.html').render(
        {
            'build_name': build_name,
            'reproducible_artifact_path': reproducible_artifact_path,
            'tag': tag,
            'commit': commit,
            'regular_buttons': regular_buttons,
            'variant_list': variant_list
        })


def do_create(tag, build_name, reproducible_artifact_path, commit, variant_arguments, all_completes):
    # Generate the single-master and multi-master templates.

    for bootstrap_variant, variant_base_args in variant_arguments.items():
        variant_prefix = pkgpanda.util.variant_prefix(bootstrap_variant)

        def make(num_masters, filename):
            num_masters_source = Source()
            num_masters_source.add_must('num_masters', str(num_masters))
            yield from gen_simple_template(
                variant_prefix,
                filename,
                variant_base_args,
                num_masters_source)

        # Single master templates
        yield from make(1, 'single-master.cloudformation.json')

        # Multi master templates
        yield from make(3, 'multi-master.cloudformation.json')

        # Advanced templates
        for os_type in ['coreos', 'el7']:
            yield from gen_advanced_template(
                variant_base_args,
                variant_prefix,
                reproducible_artifact_path,
                os_type)

    # Button page linking to the basic templates.
    button_page = gen_buttons(build_name, reproducible_artifact_path, tag, commit, variant_arguments)
    yield {
        'channel_path': 'aws.html',
        'local_content': button_page,
        'content_type': 'text/html; charset=utf-8'}

    # This renders the infra template only, which has no difference between CE and EE
    yield from gen_supporting_template()
