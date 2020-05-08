"""AWS Image Creation, Management, Testing"""

import json
from copy import deepcopy
from typing import Tuple

import boto3
import botocore.exceptions
import pkg_resources
import yaml
from pkg_resources import resource_string
from retrying import retry

import gen
import gen.build_deploy.util as util
import pkgpanda.util
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
        'ip6_detect_contents': get_ip_detect('aws6'),
        'exhibitor_explicit_keys': 'false',
        'cluster_name': Late('{ "Ref" : "AWS::StackName" }'),
        'master_discovery': 'master_http_loadbalancer',
        # The cloud_config template variables pertaining to "cloudformation.json"
        'master_cloud_config': '{{ master_cloud_config }}',
        'agent_private_cloud_config': '{{ slave_cloud_config }}',
        'agent_public_cloud_config': '{{ slave_public_cloud_config }}',
        # template variable for the generating advanced template cloud configs
        'cloud_config': '{{ cloud_config }}',
        'rexray_config_preset': 'aws',
        'fault_domain_detect_contents': yaml.dump(
            pkg_resources.resource_string('gen', 'fault-domain-detect/cloud.sh').decode()),
    },
    'conditional': {
        'oauth_available': {
            'true': {
                'must': {
                    'oauth_enabled': Late('{ "Ref" : "OAuthEnabled" }'),
                    'adminrouter_auth_enabled': Late('{ "Ref" : "OAuthEnabled" }'),
                }
            },
            'false': {}
        },
        'licensing_enabled': {
            'true': {
                'must': {
                    'license_key_contents': Late('{ "Ref" : "LicenseKey" }'),
                },
                'secret': [
                    'license_key_contents',
                ],
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

# Core OS AMIS from: https://github.com/dcos/dcos-images/blob/62f97aa3cada6d29356003ee6a01c7c94a5f5433/coreos/1967.6.0/aws/DCOS-1.12.2/docker-18.06.1/dcos_images.yaml # noqa
# RHEL 7 AMIS from: https://github.com/dcos/dcos-images/blob/9c231811a8d7f5b925ea405f928b7c2b3182bae6/rhel/7.6/aws/DCOS-1.12.0/docker-1.13.1.git8633870/selinux_disabled/dcos_images.yaml # noqa
# natami is from: https://aws.amazon.com/amazon-linux-ami/2018.03-release-notes/ instances labelled amzn-ami-vpc-nat-hvm

region_to_ami_map = {
    'ap-northeast-1': {
        'coreos': 'ami-061659fcdbb942671',
        'stable': 'ami-0ffd2ee15ceabef65',
        'el7': 'ami-0bfe52d6d145c674e',
        'el7prereq': 'ami-0bfe52d6d145c674e',
        'natami': 'ami-00d29e4cb217ae06b'
    },
    'ap-southeast-1': {
        'coreos': 'ami-030cef2acc6e5377f',
        'stable': 'ami-02e06ba544feb3f51',
        'el7': 'ami-024ac75903e3114f1',
        'el7prereq': 'ami-024ac75903e3114f1',
        'natami': 'ami-01514bb1776d5c018'
    },
    'ap-southeast-2': {
        'coreos': 'ami-08b526947c08b5842',
        'stable': 'ami-07809279cd1e43478',
        'el7': 'ami-0a81a425ed8ebf3c9',
        'el7prereq': 'ami-0a81a425ed8ebf3c9',
        'natami': 'ami-062c04ec46aecd204'
    },
    'eu-central-1': {
        'coreos': 'ami-0d1523a303dd37067',
        'stable': 'ami-06c600855f8f21e97',
        'el7': 'ami-0e6000758f18fb6be',
        'el7prereq': 'ami-0e6000758f18fb6be',
        'natami': 'ami-06a5303d47fbd8c60'
    },
    'eu-west-1': {
        'coreos': 'ami-07c25af0e918ce3c1',
        'stable': 'ami-0539ccccd1e371d4b',
        'el7': 'ami-0569e7216584320c6',
        'el7prereq': 'ami-0569e7216584320c6',
        'natami': 'ami-024107e3e3217a248'
    },
    'sa-east-1': {
        'coreos': 'ami-005ce0c51d9e43786',
        'stable': 'ami-0af8dc7533e9698e2',
        'el7': 'ami-0b34096d89569829a',
        'el7prereq': 'ami-0b34096d89569829a',
        'natami': 'ami-057f5d52ff7ae75ae'
    },
    'us-east-1': {
        'coreos': 'ami-07cce92cad14cc238',
        'stable': 'ami-08511d0b9ed33a795',
        'el7': 'ami-0da3316c3c6eb42b0',
        'el7prereq': 'ami-0da3316c3c6eb42b0',
        'natami': 'ami-00a9d4a05375b2763'
    },
    'us-west-1': {
        'coreos': 'ami-04b8d2ccf0bf3a6eb',
        'stable': 'ami-08bcbb80bb680b5f2',
        'el7': 'ami-074a555b65ca3c76e',
        'el7prereq': 'ami-074a555b65ca3c76e',
        'natami': 'ami-097ad469381034fa2'
    },
    'us-west-2': {
        'coreos': 'ami-018b1e7ac21df62b9',
        'stable': 'ami-0235ac99b19539293',
        'el7': 'ami-093949a7969be18da',
        'el7prereq': 'ami-093949a7969be18da',
        'natami': 'ami-0b840e8a1ce4cdf15'
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
    ExecStartPre=/opt/mesosphere/bin/dcos-check-runner check node-poststart
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
    client = boto3.session.Session().client('cloudformation')
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
    for filename in results.stable_artifacts:
        yield {
            'reproducible_path': filename,
            'local_path': filename,
        }


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
    supported_os = ('coreos', 'el7')
    if cc_params['os_type'] not in supported_os:
        raise RuntimeError('Unsupported os_type: {}'.format(cc_params['os_type']))
    elif cc_params['os_type'] == 'coreos':
        extra_templates += ['coreos-aws/cloud-config.yaml', 'coreos/cloud-config.yaml']
        cloud_init_implementation = 'coreos'
    elif cc_params['os_type'] == 'el7':
        cloud_init_implementation = 'canonical'
        cc_params['os_type'] = 'el7prereq'

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
        local_source.add_must('region_to_ami_mapping', gen_ami_mapping({"coreos", "el7", "el7prereq"}))
        params = cf_instance_groups[node_template_id]
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
                                              deepcopy(params))
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
                                          deepcopy(params))
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
            yaml.safe_load(gen.template.parse_str(late_services).render(deepcopy(params))))

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
