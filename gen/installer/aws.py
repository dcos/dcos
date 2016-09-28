"""AWS Image Creation, Management, Testing"""

import json
import logging
import re
from copy import deepcopy

import botocore.exceptions
import yaml
from pkg_resources import resource_string
from retrying import retry

import gen
import gen.installer.util as util
import pkgpanda.util
import release
import release.storage

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
        'coreos': 'ami-965899f7',
        'stable': 'ami-965899f7',
        'el7': 'ami-264f8747',
        'natami': 'ami-55c29e54'
    },
    'ap-southeast-1': {
        'coreos': 'ami-3120fe52',
        'stable': 'ami-3120fe52',
        'el7': 'ami-0765bd64',
        'natami': 'ami-b082dae2'
    },
    'ap-southeast-2': {
        'coreos': 'ami-b1291dd2',
        'stable': 'ami-b1291dd2',
        'el7': 'ami-3f1a2c5c',
        'natami': 'ami-996402a3'
    },
    'eu-central-1': {
        'coreos': 'ami-3ae31555',
        'stable': 'ami-3ae31555',
        'el7': 'ami-846e9eeb',
        'natami': 'ami-204c7a3d'
    },
    'eu-west-1': {
        'coreos': 'ami-b7cba3c4',
        'stable': 'ami-b7cba3c4',
        'el7': 'ami-250c7f56',
        'natami': 'ami-3760b040'
    },
    'sa-east-1': {
        'coreos': 'ami-61e3750d',
        'stable': 'ami-61e3750d',
        'el7': 'ami-0e019062',
        'natami': 'ami-b972dba4'
    },
    'us-east-1': {
        'coreos': 'ami-6d138f7a',
        'stable': 'ami-6d138f7a',
        'el7': 'ami-47096750',
        'natami': 'ami-4c9e4b24'
    },
    'us-gov-west-1': {
        'coreos': 'ami-b712acd6',
        'stable': 'ami-b712acd6',
        'el7': '',
        'natami': ''
    },
    'us-west-1': {
        'coreos': 'ami-ee57148e',
        'stable': 'ami-ee57148e',
        'el7': 'ami-e4afe284',
        'natami': 'ami-2b2b296e'
    },
    'us-west-2': {
        'coreos': 'ami-dc6ba3bc',
        'stable': 'ami-dc6ba3bc',
        'el7': 'ami-ab07d1cb',
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

groups = {
    'master': (
        'master', {
            'report_name': 'MasterServerGroup',
            's3_bucket': '{ "Ref" : "ExhibitorS3Bucket" }',
            's3_prefix': '{ "Ref" : "AWS::StackName" }',
            'exhibitor_storage_backend': 'aws_s3',
            'master_role': '{ "Ref" : "MasterRole" }',
            'agent_role': '',
            'exhibitor_address': '{ "Fn::GetAtt" : [ "InternalMasterLoadBalancer", "DNSName" ] }',
        }),
    'pub-agent': (
        'slave_public', {
            'report_name': 'PublicAgentServerGroup',
            'master_role': '',
            'agent_role': '{ "Ref" : "PublicAgentRole" }',
            'exhibitor_storage_backend': 'agent_only_group_no_exhibitor',
            'exhibitor_address': '{ "Ref" : "InternalMasterLoadBalancerDnsName" }',
        }),
    'priv-agent': (
        'slave', {
            'report_name': 'PrivateAgentServerGroup',
            'master_role': '',
            'agent_role': '{ "Ref" : "PrivateAgentRole" }',
            'exhibitor_storage_backend': 'agent_only_group_no_exhibitor',
            'exhibitor_address': '{ "Ref" : "InternalMasterLoadBalancerDnsName" }',
        })
}

AWS_REF_REGEX = re.compile(r"(?P<before>.*)(?P<ref>{ .* })(?P<after>.*)")


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


def get_cloudformation_s3_url():
    assert release._config is not None
    # TODO(cmaloney): HACK. Stashing and pulling the config from release/__init__.py
    # is definitely not the right way to do this.

    if 'options' not in release._config:
        raise RuntimeError("No options section in configuration")

    if 'cloudformation_s3_url' not in release._config['options']:
        raise RuntimeError("No options.cloudformation_s3_url section in configuration")

    # TODO(cmaloney): get_session shouldn't live in release.storage
    return release._config['options']['cloudformation_s3_url']


def transform(line):
    m = AWS_REF_REGEX.search(line)
    # no splitting necessary
    if not m:
        return "%s,\n" % (json.dumps(line + '\n'))

    before = m.group('before')
    ref = m.group('ref')
    after = m.group('after')

    transformed_before = "%s" % (json.dumps(before))
    transformed_ref = ref
    transformed_after = "%s" % (json.dumps(after))
    return "%s, %s, %s, %s,\n" % (transformed_before, transformed_ref, transformed_after, '"\\n"')


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


def _as_artifact_and_pkg(variant_prefix, filename, gen_out):
    yield _as_cf_artifact("{}{}".format(variant_prefix, filename), gen_out.cloudformation)
    yield {'packages': util.cluster_to_extra_packages(gen_out.results.cluster_packages)}


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


def make_advanced_bunch(variant_args, template_name, cc_params):
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

    cc_package_files = [
        '/etc/cfn_signal_metadata',
        '/etc/adminrouter.env',
        '/etc/dns_config',
        '/etc/exhibitor',
        '/etc/mesos-master-provider']

    if cc_params['node_type'] == 'master':
        cc_package_files.append('/etc/aws_dnsnames')

    results = gen.generate(
        arguments=variant_args,
        extra_templates=extra_templates,
        cc_package_files=cc_package_files)

    cloud_config = results.templates['cloud-config.yaml']

    # Add general services
    cloud_config = results.utils.add_services(cloud_config, cloud_init_implementation)

    cc_variant = deepcopy(cloud_config)
    cc_variant = results.utils.add_units(
        cc_variant,
        yaml.load(gen.template.parse_str(late_services).render(cc_params)),
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

    return gen.Bunch({
        'cloudformation': cloudformation,
        'results': results
    })


def get_s3_url_prefix(arguments, reproducible_artifact_path) -> str:
    assert reproducible_artifact_path, "reproducible_artifact_path must not be empty"
    if 'cloudformation_s3_url' in arguments:
        # Caller is `dcos_generate_config.sh --aws-cloudformation`
        url = arguments['cloudformation_s3_url'] + '/cloudformation'
        return url
    else:
        # Caller is release create
        url = get_cloudformation_s3_url() + '/{}/cloudformation'.format(reproducible_artifact_path)
        return url


def gen_advanced_template(arguments, variant_prefix, reproducible_artifact_path, os_type):
    cloudformation_full_s3_url = get_s3_url_prefix(arguments, reproducible_artifact_path)

    for node_type in ['master', 'priv-agent', 'pub-agent']:
        # TODO(cmaloney): This forcibly overwriting arguments might overwrite a user set argument
        # without noticing (such as exhibitor_storage_backend)
        node_template_id, node_args = groups[node_type]
        node_args = deepcopy(node_args)
        node_args.update(arguments)
        node_args['os_type'] = os_type
        node_args['region_to_ami_mapping'] = gen_ami_mapping({"coreos", "el7"})
        params = deepcopy(cf_instance_groups[node_template_id])
        params['report_name'] = node_args.pop('report_name')
        params['os_type'] = os_type
        params['node_type'] = node_type
        template_key = 'advanced-{}'.format(node_type)
        template_name = template_key + '.json'

        def _as_artifact(filename, gen_out):
            yield from _as_artifact_and_pkg(variant_prefix, filename, gen_out)

        if node_type == 'master':
            for num_masters in [1, 3, 5, 7]:
                master_tk = '{}-{}-{}'.format(os_type, template_key, num_masters)
                print('Building {} {} for num_masters = {}'.format(os_type, node_type, num_masters))
                node_args['num_masters'] = str(num_masters)
                bunch = make_advanced_bunch(node_args,
                                            template_name,
                                            params)
                yield from _as_artifact('{}.json'.format(master_tk), bunch)

                # Zen template corresponding to this number of masters
                yield _as_cf_artifact(
                    '{}{}-zen-{}.json'.format(variant_prefix, os_type, num_masters),
                    render_cloudformation_transform(
                        resource_string("gen", "aws/templates/advanced/zen.json").decode(),
                        variant_prefix=variant_prefix,
                        reproducible_artifact_path=reproducible_artifact_path,
                        cloudformation_full_s3_url=cloudformation_full_s3_url,
                        **bunch.results.arguments))
        else:
            node_args['num_masters'] = "1"
            node_args['nat_ami_mapping'] = gen_ami_mapping({"natami"})
            bunch = make_advanced_bunch(node_args,
                                        template_name,
                                        params)
            yield from _as_artifact('{}-{}'.format(os_type, template_name), bunch)


def gen_templates(arguments):
    results = gen.generate(
        arguments=arguments,
        extra_templates=[
            'aws/templates/cloudformation.json',
            'aws/dcos-config.yaml',
            'coreos-aws/cloud-config.yaml',
            'coreos/cloud-config.yaml'],
        cc_package_files=[
            '/etc/cfn_signal_metadata',
            '/etc/adminrouter.env',
            '/etc/ui-config.json',
            '/etc/dns_config',
            '/etc/exhibitor',
            '/etc/mesos-master-provider',
            '/etc/aws_dnsnames'])

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
            yaml.load(gen.template.parse_str(late_services).render(params)))

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

    print("Validating CloudFormation")
    validate_cf(cloudformation)

    return gen.Bunch({
        'cloudformation': cloudformation,
        'results': results
    })


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
            s3_url = get_s3_url_prefix(arguments, reproducible_artifact_path)
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


def do_create(tag, build_name, reproducible_artifact_path, commit, variant_arguments, all_bootstraps):
    # Generate the single-master and multi-master templates.

    for bootstrap_variant, variant_base_args in variant_arguments.items():
        # Setup base arguments
        args = deepcopy(variant_base_args)
        args['exhibitor_address'] = '{ "Fn::GetAtt" : [ "InternalMasterLoadBalancer", "DNSName" ] }'
        args['s3_bucket'] = '{ "Ref" : "ExhibitorS3Bucket" }'
        args['s3_prefix'] = '{ "Ref" : "AWS::StackName" }'
        args['exhibitor_storage_backend'] = 'aws_s3'
        args['master_role'] = '{ "Ref" : "MasterRole" }'
        args['agent_role'] = '{ "Ref" : "SlaveRole" }'
        args['region_to_ami_mapping'] = gen_ami_mapping({"stable"})
        args['nat_ami_mapping'] = gen_ami_mapping({"natami"})

        variant_prefix = pkgpanda.util.variant_prefix(bootstrap_variant)

        def make(gen_args, filename):
            gen_out = gen_templates(gen_args)
            yield from _as_artifact_and_pkg(variant_prefix, filename, gen_out)

        # Single master templates
        single_args = deepcopy(args)
        single_args['num_masters'] = "1"
        yield from make(single_args, 'single-master.cloudformation.json')

        # Multi master templates
        multi_args = deepcopy(args)
        multi_args['num_masters'] = "3"
        yield from make(multi_args, 'multi-master.cloudformation.json')

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
