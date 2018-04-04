"""Azure Image Creation, Management, Testing"""

import json
import re
import sys
import urllib
from copy import deepcopy

import pkg_resources
import yaml

import gen
import gen.build_deploy.util as util
import gen.template
import pkgpanda.build
from gen.internals import Late, Source
from pkgpanda.constants import cloud_config_yaml
from pkgpanda.util import split_by_token

# TODO(cmaloney): Make it so the template only completes when services are properly up.
late_services = ""

ILLEGAL_ARM_CHARS_PATTERN = re.compile("[']")

DOWNLOAD_URL_TEMPLATE = ("{download_url}{reproducible_artifact_path}/azure/{arm_template_name}")

INSTANCE_GROUPS = {
    'master': {
        'report_name': 'MasterServerGroup',
        'roles': ['master', 'azure_master']
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


def validate_provider(provider):
    assert provider == 'azure'


azure_base_source = Source(entry={
    'validate': [
        validate_provider
    ],
    'default': {
        'platform': 'azure',
        'enable_docker_gc': 'true'
    },
    'must': {
        'resolvers': '["168.63.129.16"]',
        'ip_detect_contents': yaml.dump(pkg_resources.resource_string('gen', 'ip-detect/azure.sh').decode()),
        'ip6_detect_contents': yaml.dump(pkg_resources.resource_string('gen', 'ip-detect/azure6.sh').decode()),
        'master_discovery': 'static',
        'exhibitor_storage_backend': 'azure',
        'master_cloud_config': '{{ master_cloud_config }}',
        'slave_cloud_config': '{{ slave_cloud_config }}',
        'slave_public_cloud_config': '{{ slave_public_cloud_config }}',
        'fault_domain_detect_contents': yaml.dump(
            pkg_resources.resource_string('gen', 'fault-domain-detect/cloud.sh').decode())
    },
    'conditional': {
        'oauth_available': {
            'true': {
                'must': {
                    'oauth_enabled': Late("[[[variables('oauthEnabled')]]]"),
                    'adminrouter_auth_enabled': Late("[[[variables('oauthEnabled')]]]"),
                }
            },
            'false': {},
        },
        'licensing_enabled': {
            'true': {
                'must': {
                    'license_key_contents': Late("[[[variables('licenseKey')]]]"),
                },
                'secret': [
                    'license_key_contents',
                ],
            },
            'false': {},
        }
    }
})


def validate_cloud_config(cc_string):
    '''
    Validate that there aren't any single quotes present since they break the
    ARM template system. Exit with an error message if any invalid characters
    are detected.

    @param cc_string: str, Cloud Configuration
    '''
    if "'" in cc_string:
        print("ERROR: Illegal cloud config string detected.", file=sys.stderr)
        print("ERROR: {} contains a `'`".format(cc_string), file=sys.stderr)
        sys.exit(1)


def transform(cloud_config_yaml_str):
    '''
    Transforms the given yaml into a list of strings which are concatenated
    together by the ARM template system. We must make it a list of strings so
    that ARM template parameters appear at the top level of the template and get
    substituted.
    '''
    cc_json = json.dumps(yaml.safe_load(cloud_config_yaml_str), sort_keys=True)

    def _quote_literals(parts):
        for part, is_param in parts:
            if is_param:
                yield part
            else:
                validate_cloud_config(part)
                yield "'{}'".format(part)

    # We're embedding this as a json string.
    return json.dumps(
        "[base64(concat('#cloud-config\n\n', " +
        ", ".join(_quote_literals(split_by_token('[[[', ']]]', cc_json, strip_token_decoration=True))) +
        "))]"
    )


def render_arm(
        arm_template,
        master_cloudconfig_yaml_str,
        slave_cloudconfig_yaml_str,
        slave_public_cloudconfig_yaml_str):

    template_str = gen.template.parse_str(arm_template).render({
        'master_cloud_config': transform(master_cloudconfig_yaml_str),
        'slave_cloud_config': transform(slave_cloudconfig_yaml_str),
        'slave_public_cloud_config': transform(slave_public_cloudconfig_yaml_str)
    })

    # Add in some metadata to help support engineers
    template_json = json.loads(template_str)
    template_json['variables']['DcosImageCommit'] = util.dcos_image_commit
    template_json['variables']['TemplateGenerationDate'] = util.template_generation_date
    return json.dumps(template_json)


def gen_templates(gen_arguments, arm_template, extra_sources):
    '''
    Render the cloud_config template given a particular set of options

    @param user_args: dict, args to pass to the gen library. These are user
                     input arguments which get filled in/prompted for.
    @param arm_template: string, path to the source arm template for rendering
                         by the gen library (e.g. 'azure/templates/azuredeploy.json')
    '''
    results = gen.generate(
        arguments=gen_arguments,
        extra_templates=['azure/' + cloud_config_yaml, 'azure/templates/' + arm_template + '.json'],
        extra_sources=[azure_base_source] + extra_sources)

    cloud_config = results.templates[cloud_config_yaml]

    # Add general services
    cloud_config = results.utils.add_services(cloud_config, 'canonical')

    # Specialize for master, slave, slave_public
    variant_cloudconfig = {}
    for variant, params in INSTANCE_GROUPS.items():
        cc_variant = deepcopy(cloud_config)

        # Add roles
        cc_variant = results.utils.add_roles(cc_variant, params['roles'] + ['azure'])

        # NOTE: If this gets printed in string stylerather than '|' the Azure
        # parameters which need to be split out for the arm to
        # interpret end up all escaped and undoing it would be hard.
        variant_cloudconfig[variant] = results.utils.render_cloudconfig(cc_variant)

    # Render the arm
    arm = render_arm(
        results.templates[arm_template + '.json'],
        variant_cloudconfig['master'],
        variant_cloudconfig['slave'],
        variant_cloudconfig['slave_public'])

    return (arm, results)


def master_list_arm_json(num_masters, varietal):
    '''
    Return a JSON string containing a list of ARM expressions for the master IP's of the cluster.

    @param num_masters: int, number of master nodes in the cluster
    @param varietal: string, indicate template varietal to build for either 'acs' or 'dcos'
    '''

    if varietal == 'dcos':
        arm_expression = "[[[reference('masterNodeNic{}').ipConfigurations[0].properties.privateIPAddress]]]"
    elif varietal == 'acs':
        arm_expression = "[[[reference(variables('masterVMNic')[{}]).ipConfigurations[0].properties.privateIPAddress]]]"
    else:
        raise ValueError("Unknown Azure varietal specified")

    return json.dumps([arm_expression.format(x) for x in range(num_masters)])


azure_dcos_source = Source({
    'must': {
        'exhibitor_azure_prefix': Late("[[[variables('uniqueName')]]]"),
        'exhibitor_azure_account_name': Late("[[[variables('storageAccountName')]]]"),
        'exhibitor_azure_account_key': Late(
            "[[[listKeys(resourceId('Microsoft.Storage/storageAccounts', "
            "variables('storageAccountName')), '2015-05-01-preview').key1]]]"),
        'cluster_name': Late("[[[variables('uniqueName')]]]")
    }
})

azure_acs_source = Source({
    'must': {
        'ui_tracking': 'false',
        'telemetry_enabled': 'false',
        'exhibitor_azure_prefix': Late("[[[variables('masterPublicIPAddressName')]]]"),
        'exhibitor_azure_account_name': Late("[[[variables('masterStorageAccountExhibitorName')]]]"),
        'exhibitor_azure_account_key': Late(
            "[[[listKeys(resourceId('Microsoft.Storage/storageAccounts', "
            "variables('masterStorageAccountExhibitorName')), '2015-06-15').key1]]]"),
        'cluster_name': Late("[[[variables('masterPublicIPAddressName')]]]"),
        'bootstrap_tmp_dir': "/var/tmp"
    }
})


def make_template(num_masters, gen_arguments, varietal, bootstrap_variant_prefix):
    '''
    Return a tuple: the generated template for num_masters and the artifact dict.

    @param num_masters: int, number of master nodes to embed in the generated template
    @param gen_arguments: dict, args to pass to the gen library. These are user
                          input arguments which get filled in/prompted for.
    @param varietal: string, indicate template varietal to build for either 'acs' or 'dcos'
    '''

    master_list_source = Source()
    master_list_source.add_must('master_list', Late(master_list_arm_json(num_masters, varietal)))
    master_list_source.add_must('num_masters', str(num_masters))

    if varietal == 'dcos':
        arm, results = gen_templates(
            gen_arguments,
            'azuredeploy',
            extra_sources=[master_list_source, azure_dcos_source])
    elif varietal == 'acs':
        arm, results = gen_templates(
            gen_arguments,
            'acs',
            extra_sources=[master_list_source, azure_acs_source])
    else:
        raise ValueError("Unknown Azure varietal specified")

    yield {
        'channel_path': 'azure/{}{}-{}master.azuredeploy.json'.format(bootstrap_variant_prefix, varietal, num_masters),
        'local_content': arm,
        'content_type': 'application/json; charset=utf-8'
    }
    for filename in results.stable_artifacts:
        yield {
            'reproducible_path': filename,
            'local_path': filename,
        }


def do_create(tag, build_name, reproducible_artifact_path, commit, variant_arguments, all_completes):
    for arm_t in ['dcos', 'acs']:
        for num_masters in [1, 3, 5]:
            for bootstrap_name, gen_arguments in variant_arguments.items():
                yield from make_template(
                    num_masters,
                    gen_arguments,
                    arm_t,
                    pkgpanda.util.variant_prefix(bootstrap_name))

    yield {
        'channel_path': 'azure.html',
        'local_content': gen_buttons(
            build_name,
            reproducible_artifact_path,
            tag,
            commit,
            next(iter(variant_arguments.values()))['azure_download_url']),
        'content_type': 'text/html; charset=utf-8'
    }


def gen_buttons(build_name, reproducible_artifact_path, tag, commit, download_url):
    '''
    Generate the button page, that is, "Deploy a cluster to Azure" page
    '''
    dcos_urls = [
        encode_url_as_param(DOWNLOAD_URL_TEMPLATE.format(
            download_url=download_url,
            reproducible_artifact_path=reproducible_artifact_path,
            arm_template_name='dcos-{}master.azuredeploy.json'.format(x)))
        for x in [1, 3, 5]]
    acs_urls = [
        encode_url_as_param(DOWNLOAD_URL_TEMPLATE.format(
            download_url=download_url,
            reproducible_artifact_path=reproducible_artifact_path,
            arm_template_name='acs-{}master.azuredeploy.json'.format(x)))
        for x in [1, 3, 5]]

    return gen.template.parse_resources('azure/templates/azure.html').render({
        'build_name': build_name,
        'tag': tag,
        'commit': commit,
        'dcos_urls': dcos_urls,
        'acs_urls': acs_urls
    })


# Escape URL characters like '/' and ':' so that it can be used with the Azure
# web endpoint of https://portal.azure.com/#create/Microsoft.Template/uri/
def encode_url_as_param(s):
    s = s.encode('utf8')
    s = urllib.parse.quote_plus(s)
    return s
