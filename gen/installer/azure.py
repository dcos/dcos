"""Azure Image Creation, Management, Testing"""

import json
import re
import sys
import urllib
from copy import deepcopy

import yaml

import gen
import gen.installer.util as util
import gen.template
import pkgpanda.build
import release
import release.storage

# TODO(cmaloney): Make it so the template only completes when services are properly up.
late_services = ""

ILLEGAL_ARM_CHARS_PATTERN = re.compile("[']")

TEMPLATE_PATTERN = re.compile('(?P<pre>.*?)\[\[\[(?P<inject>.*?)\]\]\]')

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


def validate_cloud_config(cc_string):
    '''
    Validate that there aren't any single quotes present since they break the
    ARM template system. Exit with an error message if any invalid characters
    are detected.

    @param cc_string: str, Cloud Configuration
    '''
    illegal_match = ILLEGAL_ARM_CHARS_PATTERN.search(cc_string)
    if illegal_match:
        print("ERROR: Illegal cloud config string detected.", file=sys.stderr)
        print("ERROR: {} matches pattern {}".format(
            illegal_match.string, illegal_match.re), file=sys.stderr)
        sys.exit(1)


def transform(cloud_config_yaml_str):
    '''
    Transforms the given yaml into a list of strings which are concatenated
    together by the ARM template system. We must make it a list of strings so
    that ARM template parameters appear at the top level of the template and get
    substituted.
    '''
    cc_json = json.dumps(yaml.load(cloud_config_yaml_str), sort_keys=True)
    arm_list = ["[base64(concat('#cloud-config\n\n', "]
    # Find template parameters and seperate them out as seperate elements in a
    # json list.
    prev_end = 0
    # TODO(JL) - Why does validate_cloud_config not operate on entire string?
    for m in TEMPLATE_PATTERN.finditer(cc_json):
        before = m.group('pre')
        param = m.group('inject')
        validate_cloud_config(before)
        arm_list.append("'{}', {},".format(before, param))
        prev_end = m.end()

    # Add the last little bit
    validate_cloud_config(cc_json[prev_end:])
    arm_list.append("'{}'))]".format(cc_json[prev_end:]))

    # We're embedding this as a json string, so json encode it and return.
    return json.dumps(''.join(arm_list))


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


def gen_templates(user_args, arm_template):
    '''
    Render the cloud_config template given a particular set of options

    @param user_args: dict, args to pass to the gen library. These are user
                     input arguments which get filled in/prompted for.
    @param arm_template: string, path to the source arm template for rendering
                         by the gen library (e.g. 'azure/templates/azuredeploy.json')
    '''
    results = gen.generate(
        arguments=user_args,
        extra_templates=['azure/cloud-config.yaml', 'azure/templates/' + arm_template + '.json'],
        cc_package_files=[
            '/etc/exhibitor',
            '/etc/exhibitor.properties',
            '/etc/adminrouter.env',
            '/etc/ui-config.json',
            '/etc/mesos-master-provider',
            '/etc/master_list'])

    cloud_config = results.templates['cloud-config.yaml']

    # Add general services
    cloud_config = results.utils.add_services(cloud_config, 'canonical')

    # Specialize for master, slave, slave_public
    variant_cloudconfig = {}
    for variant, params in INSTANCE_GROUPS.items():
        cc_variant = deepcopy(cloud_config)

        # TODO(cmaloney): Add the dcos-arm-signal service here
        # cc_variant = results.utils.add_units(
        #     cc_variant,
        #     yaml.load(gen.template.parse_str(late_services).render(params)))

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

    return gen.Bunch({
        'arm': arm,
        'results': results
    })


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


def make_template(num_masters, gen_arguments, varietal, bootstrap_variant_prefix):
    '''
    Return a tuple: the generated template for num_masters and the artifact dict.

    @param num_masters: int, number of master nodes to embed in the generated template
    @param gen_arguments: dict, args to pass to the gen library. These are user
                          input arguments which get filled in/prompted for.
    @param varietal: string, indicate template varietal to build for either 'acs' or 'dcos'
    '''

    gen_arguments['master_list'] = master_list_arm_json(num_masters, varietal)
    args = deepcopy(gen_arguments)

    if varietal == 'dcos':
        args['exhibitor_azure_prefix'] = "[[[variables('uniqueName')]]]"
        args['exhibitor_azure_account_name'] = "[[[variables('storageAccountName')]]]"
        args['exhibitor_azure_account_key'] = ("[[[listKeys(resourceId('Microsoft.Storage/storageAccounts', "
                                               "variables('storageAccountName')), '2015-05-01-preview').key1]]]")
        args['cluster_name'] = "[[[variables('uniqueName')]]]"
        dcos_template = gen_templates(args, 'azuredeploy')
    elif varietal == 'acs':
        args['exhibitor_azure_prefix'] = "[[[variables('masterPublicIPAddressName')]]]"
        args['exhibitor_azure_account_name'] = "[[[variables('masterStorageAccountExhibitorName')]]]"
        args['exhibitor_azure_account_key'] = ("[[[listKeys(resourceId('Microsoft.Storage/storageAccounts', "
                                               "variables('masterStorageAccountExhibitorName')), '2015-06-15').key1]]]")
        args['cluster_name'] = "[[[variables('masterPublicIPAddressName')]]]"
        dcos_template = gen_templates(args, 'acs')
    else:
        raise ValueError("Unknown Azure varietal specified")

    yield {'packages': dcos_template.results.config_package_ids}
    yield {
        'channel_path': 'azure/{}{}-{}master.azuredeploy.json'.format(bootstrap_variant_prefix, varietal, num_masters),
        'local_content': dcos_template.arm,
        'content_type': 'application/json; charset=utf-8'
    }


def do_create(tag, build_name, reproducible_artifact_path, commit, variant_arguments, all_completes):
    for arm_t in ['dcos', 'acs']:
        for num_masters in [1, 3, 5]:
            for bootstrap_name, gen_arguments in variant_arguments.items():
                gen_args = deepcopy(gen_arguments)
                if arm_t == 'acs':
                    gen_args['ui_tracking'] = 'false'
                    gen_args['telemetry_enabled'] = 'false'
                yield from make_template(
                    num_masters,
                    gen_args,
                    arm_t,
                    pkgpanda.util.variant_prefix(bootstrap_name))

    yield {
        'channel_path': 'azure.html',
        'local_content': gen_buttons(build_name, reproducible_artifact_path, tag, commit),
        'content_type': 'text/html; charset=utf-8'
    }


def gen_buttons(build_name, reproducible_artifact_path, tag, commit):
    '''
    Generate the button page, that is, "Deploy a cluster to Azure" page
    '''
    dcos_urls = [
        encode_url_as_param(DOWNLOAD_URL_TEMPLATE.format(
            download_url=get_download_url(),
            reproducible_artifact_path=reproducible_artifact_path,
            arm_template_name='dcos-{}master.azuredeploy.json'.format(x)))
        for x in [1, 3, 5]]
    acs_urls = [
        encode_url_as_param(DOWNLOAD_URL_TEMPLATE.format(
            download_url=get_download_url(),
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


def get_download_url():
    assert release._config is not None
    # TODO: HACK. Stashing and pulling the config from release/__init__.py
    # is definitely not the right way to do this.
    # See also gen/installer/aws.py#get_cloudformation_s3_url

    if 'storage' not in release._config:
        raise RuntimeError("No storage section in configuration")

    if 'azure' not in release._config['storage']:
        # No azure storage, inject a fake url for now so if people want to use
        # the azure templates they know to come look here.
        return "https://AZURE NOT CONFIGURED, ADD A storage.azure section to " \
            "dcos-release.config.yaml to use the Azure templates"

    if 'download_url' not in release._config['storage']['azure']:
        raise RuntimeError("No download_url section in azure configuration")

    download_url = release._config['storage']['azure']['download_url']

    if not download_url.endswith('/'):
        raise RuntimeError("Azure download_url must end with a '/'")

    return download_url
