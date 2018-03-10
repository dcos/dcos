"""DC/OS release management

1. Build and upload a DC/OS release to a release URL
2. Move a latest version of a release from one place to another

Co-ordinates across all gen.build_deploy
"""

import argparse
import copy
import importlib
import inspect
import json
import logging
import os.path
import subprocess
import sys
from distutils.version import LooseVersion
from typing import Optional

import pkg_resources

import gen.build_deploy.util as util
import pkgpanda
import pkgpanda.build
import pkgpanda.util
import release.storage
from gen.calc import DCOS_VERSION
from pkgpanda.constants import DOCKERFILE_DIR
from pkgpanda.util import is_windows, logger

if is_windows:
    # DC/OS is not supported on AWS at this time.
    provider_names = ['azure', 'bash']
else:
    provider_names = ['aws', 'azure', 'bash']


class ConfigError(Exception):
    pass


def expand_env_vars(config):
    # Iterate recursively through config dictionaries, mapping any string keys that begin with `$` into
    # env vars.
    # If they don't begin with $ then skip.
    # If they begin with \$ simply replace with $.
    if isinstance(config, dict):
        return {key: expand_env_vars(value) for key, value in config.items()}
    elif isinstance(config, list):
        return [expand_env_vars(item) for item in config]
    elif isinstance(config, str):
        # Env variable replacement
        # Escaped $
        if config.startswith('$$'):
            return config[1:]
        elif config.startswith('$'):
            key = config[1:]
            if key not in os.environ:
                logging.error("Requested environment variable {} in config isn't set in the "
                              "environment".format(key))
                return ''
            return os.environ[key]

        # No processing to do
        return config
    else:
        # Not a known type. Skipping
        return config


def load_config(filename):
    return expand_env_vars(pkgpanda.util.load_yaml(filename))


def strip_locals(data):
    """Returns a dictionary with all keys that begin with local_ removed.

    If data is a dictionary, recurses through cleaning the keys of that as well.
    If data is a list, any dictionaries it contains are cleaned. Any lists it
    contains are recursively handled in the same way.

    """

    if isinstance(data, dict):
        return {key: strip_locals(value) for key, value in data.items()
                if not (isinstance(key, str) and key.startswith('local_'))}
    elif isinstance(data, list):
        data = [strip_locals(item) for item in data]

    return data


def to_json(data):
    """Return a JSON string representation of data.

    If data is a dictionary, None is replaced with 'null' in its keys and,
    recursively, in the keys of any dictionary it contains. This is done to
    allow the dictionary to be sorted by key before being written to JSON.

    """
    def none_to_null(obj):
        try:
            items = obj.items()
        except AttributeError:
            return obj
        # Don't make any ambiguities by requiring null to not be a key.
        assert 'null' not in obj
        return {'null' if key is None else key: none_to_null(val) for key, val in items}

    return json.dumps(none_to_null(data), indent=2, sort_keys=True)


def from_json(json_str):
    """Reverses to_json"""

    def null_to_none(obj):
        try:
            items = obj.items()
        except AttributeError:
            return obj
        return {None if key == 'null' else key: null_to_none(val) for key, val in items}

    return null_to_none(json.loads(json_str))


def load_providers():
    return {name: importlib.import_module("gen.build_deploy." + name)
            for name in provider_names}


# Transforms artifact definitions from the Release Manager into sets of commands
# the storage providers understand, adding in the full path prefixes as needed
# so storage provides just have to know how to operate on paths rather than
# have all the logic about channels and repositories.
class Repository():

    def __init__(self, repository_path, channel_name: Optional[str], unique_id):
        if not repository_path:
            raise ValueError("repository_path must be a non-empty string. channel_name may be None though.")

        assert not repository_path.endswith('/')
        if channel_name is not None:
            assert len(channel_name) > 0, "For an empty channel name pass None"
            assert not channel_name.startswith('/')
            assert not channel_name.endswith('/')
        assert not unique_id.startswith('/') and not unique_id.endswith('/')

        self.__repository_path = repository_path
        self.__channel_name = channel_name
        self.__unique_id = unique_id

    @property
    def path_prefix(self):
        return self.__repository_path + '/'

    @property
    def path_channel_prefix(self):
        return self.path_prefix + self.channel_prefix

    @property
    def reproducible_artifact_path(self):
        return self.path_channel_prefix + self.__unique_id + '/'

    @property
    def channel_prefix(self):
        return self.__channel_name + '/' if self.__channel_name else ''

    # TODO(cmaloney): This function is too big. Break it into testable chunks.
    # TODO(cmaloney): Assert the same path/destination_path is never used twice.
    def make_commands(self, metadata):
        stage1 = []
        stage2 = []

        def process_artifact(artifact, base_artifact):
            # First destination is upload
            # All other destinations are copies from first destination.
            upload_path = None

            def add_dest(destination_path, is_reproducible):
                nonlocal upload_path

                # First action -> upload
                # Future actions -> copy from upload / first action
                if upload_path is not None:
                    return {
                        'method': 'copy',
                        'if_not_exists': is_reproducible,
                        'args': {
                            'source_path': upload_path,
                            'destination_path': destination_path}}

                # Always set upload_path
                upload_path = destination_path

                # Copy inside the repository if we have a copy_from source.
                if 'local_copy_from' in artifact:
                    return {
                        'method': 'copy',
                        'if_not_exists': is_reproducible,
                        'args': {
                            'source_path': artifact['local_copy_from'],
                            'destination_path': destination_path}}
                else:
                    # Upload from local machine.
                    action = {
                        'method': 'upload',
                        'if_not_exists': is_reproducible,
                        'args': {
                            'destination_path': destination_path,
                            'no_cache': not is_reproducible}}
                    if 'local_path' in artifact:
                        # local_path and local_content are mutually exclusive / can only use one at a time.
                        assert 'local_content' not in artifact
                        action['args']['local_path'] = artifact['local_path']
                    elif 'local_content' in artifact:
                        action['args']['blob'] = artifact['local_content'].encode('utf-8')
                    else:
                        raise ValueError("local_path or local_content must be used as original "
                                         "source for {}".format(destination_path))

                    if 'content_type' in artifact:
                        action['args']['content_type'] = artifact['content_type']
                    return action

            assert artifact.keys() <= {'reproducible_path', 'channel_path', 'content_type',
                                       'local_path', 'local_content', 'local_copy_from'}, artifact

            action_count = 0
            if 'reproducible_path' in artifact:
                action_count += 1
                stage1.append(add_dest(self.path_prefix + artifact['reproducible_path'], True))

            if 'channel_path' in artifact:
                channel_path = artifact['channel_path']
                action_count += 2
                stage1.append(add_dest(self.reproducible_artifact_path + channel_path, False))
                stage2.append(add_dest(self.path_channel_prefix + channel_path, False))

            # Must have done at least one thing with the artifact (reproducible_path or channel_path).
            assert action_count > 0

        for artifact in metadata['core_artifacts']:
            process_artifact(artifact, True)
        for artifact in metadata['channel_artifacts']:
            process_artifact(artifact, False)

        process_artifact({
            'channel_path': 'metadata.json',
            'content_type': 'application/json; charset=utf-8',
            'local_content': to_json(strip_locals(metadata))
        }, False)

        return {
            'stage1': stage1,
            'stage2': stage2,
        }


def make_package_filename(package_id_str):
    package_id = pkgpanda.PackageId(package_id_str)
    extension = '.tar.xz'
    if package_id.version == 'setup':
        extension = '.dcos_config'
    return 'packages/{}/{}{}'.format(package_id.name, package_id_str, extension)


def get_package_artifact(package_id_str):
    package_filename = make_package_filename(package_id_str)
    return {
        'reproducible_path': package_filename,
        'local_path': 'packages/cache/' + package_filename}


def get_gen_package_artifact(package_id_str):
    package_filename = make_package_filename(package_id_str)
    return {
        'reproducible_path': package_filename,
        'local_path': package_filename}


def make_bootstrap_artifacts(bootstrap_id, package_ids, variant_name, artifact_prefix):
    bootstrap_filename = "{}.bootstrap.tar.xz".format(bootstrap_id)
    active_filename = "{}.active.json".format(bootstrap_id)
    active_local_path = artifact_prefix + '/bootstrap/' + active_filename
    latest_filename = "{}bootstrap.latest".format(pkgpanda.util.variant_prefix(variant_name))
    latest_complete_filename = "{}complete.latest.json".format(pkgpanda.util.variant_prefix(variant_name))

    # Assert that the bootstrap active packages are in the package list.
    with open(active_local_path) as f:
        missing_packages = set(json.load(f)) - set(package_ids)
    assert len(missing_packages) == 0, (
        'variant {} has bootstrap packages missing from the package list: {}'.format(
            pkgpanda.util.variant_name(variant_name),
            missing_packages,
        )
    )

    yield {
        'reproducible_path': 'bootstrap/' + bootstrap_filename,
        'local_path': artifact_prefix + '/bootstrap/' + bootstrap_filename
    }
    yield {
        'reproducible_path': 'bootstrap/' + active_filename,
        'local_path': active_local_path
    }
    yield {
        'channel_path': latest_filename,
        'local_path': artifact_prefix + '/bootstrap/' + latest_filename
    }
    yield {
        'channel_path': latest_complete_filename,
        'local_path': artifact_prefix + '/complete/' + latest_complete_filename
    }


def make_stable_artifacts(cache_repository_url, tree_variants):
    metadata = {
        "commit": util.dcos_image_commit,
        "core_artifacts": [],
        "packages": set()
    }

    # TODO(cmaloney): Rather than guessing / reverse-engineering all these paths
    # have do_build_packages get them directly from pkgpanda
    with logger.scope("Building packages"):
        try:
            all_completes = do_build_packages(cache_repository_url, tree_variants)
        except pkgpanda.build.BuildError as ex:
            logger.error("Failure building package(s): {}".format(ex))
            raise

    # The installer and util are built bootstraps, but not a DC/OS variants. We use
    # iteration over the complete_dict to enumerate all variants a whole lot,
    # so explicity remove installer/util here so people don't accidentally hit it.
    # TODO: make this into a tree option
    complete_dict = dict()
    for name, info in copy.copy(all_completes).items():
        if name is not None and (name.endswith('installer') or name.endswith('util')):
            continue
        complete_dict[name] = info

    metadata["complete_dict"] = complete_dict
    metadata["all_completes"] = all_completes

    metadata["bootstrap_dict"] = {k: v['bootstrap'] for k, v in complete_dict.items()}
    metadata["all_bootstraps"] = {k: v['bootstrap'] for k, v in all_completes.items()}

    def add_file(info):
        metadata["core_artifacts"].append(info)

    def add_package(package_id):
        if package_id in metadata['packages']:
            return
        metadata['packages'].add(package_id)
        add_file(get_package_artifact(package_id))

    # Add the bootstrap, active.json, packages as reproducible_path artifacts
    # Add the <variant>.bootstrap.latest as a channel_path
    for name, info in sorted(all_completes.items(), key=lambda kv: pkgpanda.util.variant_str(kv[0])):
        for file in make_bootstrap_artifacts(info['bootstrap'], info['packages'], name, 'packages/cache'):
            add_file(file)

        # Add all the packages which haven't been added yet
        for package_id in sorted(info['packages']):
            add_package(package_id)

    # Sets aren't json serializable, so transform to a list for future use.
    metadata['packages'] = list(sorted(metadata['packages']))

    return metadata


def built_resource_to_artifacts(built_resource: dict):
    # Type switch
    if 'packages' in built_resource:
        return [get_gen_package_artifact(package) for package in built_resource['packages']]
    else:
        assert 'packages' not in built_resource
        return [built_resource]


# Generate provider templates against the bootstrap id, capturing the
# needed packages.
# {
#   <provider_name>: {
#     'extra_packages': [],
#     'files': [{
#        # NOTE: May specify a list of known_names
#       'known_path': 'cloudformation/single-master.cloudformation.json',
#       'stable_path': 'cloudformation/{}.cloudformation.json',
#        # NOTE: Only one of content or content_file is allowed
#       'content': '',
#       'content_file': '',
#       }]}}
def make_channel_artifacts(metadata):
    artifacts = [{
        'channel_path': 'version',
        'local_content': DCOS_VERSION,
        'content_type': 'text/plain; charset=utf-8',
    }]

    # Set logging to debug so we get gen error messages, since those are
    # logging.DEBUG currently to not show up when people are using `--genconf`
    # and friends.
    # TODO(cmaloney): Remove this and make the core bits of gen, code log at
    # the proper info / warning / etc. level.
    log = logging.getLogger()
    original_log_level = log.getEffectiveLevel()
    log.setLevel(logging.DEBUG)

    provider_data = {}
    providers = load_providers()
    for name, module in sorted(providers.items()):
        bootstrap_url = metadata['repository_url']

        # If the particular provider has its own storage by the same name then
        # Use the storage provider rather
        if name in metadata['storage_urls']:
            bootstrap_url = metadata['storage_urls'][name] + metadata['repository_path']

        variant_arguments = dict()

        for variant, variant_info in metadata['complete_dict'].items():
            variant_arguments[variant] = copy.deepcopy({
                'bootstrap_url': bootstrap_url,
                'provider': name,
                'bootstrap_id': variant_info['bootstrap'],
                'bootstrap_variant': pkgpanda.util.variant_prefix(variant),
                'package_ids': json.dumps(variant_info['packages'])
            })

            # Load additional default variant arguments out of gen_extra
            if os.path.exists('gen_extra/calc.py'):
                mod = importlib.machinery.SourceFileLoader('gen_extra.calc', 'gen_extra/calc.py').load_module()
                variant_arguments[variant].update(mod.provider_template_defaults)

        # Add templates for the default variant.
        # Use keyword args to make not matching ordering a loud error around changes.
        with logger.scope("Creating {} deploy tools".format(module.__name__)):
            # TODO(cmaloney): Cleanup by just having this make and pass another source.
            module_specific_variant_arguments = copy.deepcopy(variant_arguments)
            for arg_dict in module_specific_variant_arguments.values():
                if module.__name__ == 'gen.build_deploy.aws':
                    arg_dict['cloudformation_s3_url_full'] = metadata['cloudformation_s3_url_full']
                elif module.__name__ == 'gen.build_deploy.azure':
                    arg_dict['azure_download_url'] = metadata['azure_download_url']
                elif module.__name__ == 'gen.build_deploy.bash':
                    pass
                else:
                    raise NotImplementedError("Unknown how to add args to deploy tool: {}".format(module.__name__))

            for built_resource in module.do_create(
                    tag=metadata['tag'],
                    build_name=metadata['build_name'],
                    reproducible_artifact_path=metadata['reproducible_artifact_path'],
                    commit=metadata['commit'],
                    variant_arguments=module_specific_variant_arguments,
                    all_completes=metadata['all_completes']):

                assert isinstance(built_resource, dict), built_resource

                # Type switch
                if 'packages' in built_resource:
                    for package in built_resource['packages']:
                        artifacts.append(get_gen_package_artifact(package))
                else:
                    assert 'packages' not in built_resource
                    artifacts.append(built_resource)

            # TODO(cmaloney): Check the provider artifacts adhere to the artifact template.
            artifacts += provider_data.get('artifacts', list())

    log.setLevel(original_log_level)

    return artifacts


def make_abs(path):
    if path[0] == '/':
        return path
    return os.getcwd() + '/' + path


def do_build_docker(name, path):
    with logger.scope("dcos/dcos-builder ({})".format(name)):
        return _do_build_docker(name, path)


def _do_build_docker(name, path):
    path_sha = pkgpanda.build.hash_folder_abs(path, os.path.dirname(path))
    container_name = 'dcos/dcos-builder:{}_dockerdir-{}'.format(name, path_sha)

    print("Attempting to pull docker:", container_name)
    pulled = False
    try:
        # TODO(cmaloney): Rather than pushing / pulling from Docker Hub upload as a build artifact.
        # the exported tarball.
        subprocess.check_call(['docker', 'pull', container_name])
        pulled = True
        # TODO(cmaloney): Differentiate different failures of running the process better here
    except subprocess.CalledProcessError:
        pulled = False

    if not pulled:
        print("Pull failed, building instead:", container_name)
        # Pull failed, build it
        subprocess.check_call(['docker', 'build', '-t', container_name, path])

        # TODO(cmaloney): Push the built docker image on successful package build to both
        # 1) commit-<commit_id>
        # 2) Dockerfile-<file_contents_sha1>
        # 3) bootstrap-<bootstrap_id>
        # So we can track back the builder id for a given commit or bootstrap id, and reproduce whatever
        # we need. The  Dockerfile-<sha1> is useful for making sure we don't rebuild more than
        # necessary.
        try:
            subprocess.check_call(['docker', 'push', container_name])
        except subprocess.CalledProcessError:
            logger.warning("docker push of dcos-builder failed. This means it will be very difficult "
                           "for this build to be reproduced (others will have a different / non-identical "
                           "base docker for most packages.")
            pass

    # mark as latest so it will be used when building packages
    # extract the docker client version string
    try:
        docker_version = subprocess.check_output(['docker', 'version', '-f', '{{.Client.Version}}']).decode()
    except subprocess.CalledProcessError:
        # If the above command fails then we know we have an older version of docker
        # Older versions of docker spit out an entirely different format
        docker_version = subprocess.check_output(['docker', 'version']).decode().split("\n")[0].split()[2]

    # only use force tag if using docker version 1.9 or earlier
    container_name_t = 'dcos/dcos-builder:{}_dockerdir-latest'.format(name)
    if LooseVersion(docker_version) < LooseVersion('1.10'):
        args = ['docker', 'tag', '-f', container_name, container_name_t]
    else:
        args = ['docker', 'tag', container_name, container_name_t]
    subprocess.check_call(args)


def _get_global_builders():
    """Find builders defined globally
    """
    res = {}

    for name in pkg_resources.resource_listdir('pkgpanda', DOCKERFILE_DIR):
        res[name] = pkg_resources.resource_filename('pkgpanda',
                                                    DOCKERFILE_DIR + name)
    return res


def _build_builders(package_store):
    """Build all builder containers required to build packages
    """
    global_builders = _get_global_builders()
    pkg_builders = package_store.builders

    overlap = set(global_builders) & set(pkg_builders)
    if overlap:
        msg_fmt = "Package-defined builders overlap with global: `{}`"
        raise pkgpanda.build.BuildError(msg_fmt.format(overlap))

    # FIXME: with python3.6 it is going to be: union_d12 = {**d1, **d2}
    all_builders = global_builders.copy()
    all_builders.update(pkg_builders)
    for name, path in all_builders.items():
        do_build_docker(name, path)


def do_build_packages(cache_repository_url, tree_variants):
    package_store = pkgpanda.build.PackageStore(os.getcwd() + '/packages',
                                                cache_repository_url)

    _build_builders(package_store)

    result = pkgpanda.build.build_tree(package_store, True, tree_variants)
    last_set = package_store.get_last_complete_set(tree_variants)
    assert last_set == result, \
        "Internal error: get_last_complete_set doesn't match the results of build_tree: {} != {}".format(
            last_set,
            result)

    return result


def get_azure_download_url(config) -> str:
    # TODO: HACK. Stashing and pulling the config from release/__init__.py
    # is definitely not the right way to do this.
    # See also gen/build_deploy/aws.py#get_cloudformation_s3_url

    if 'storage' not in config:
        raise RuntimeError("No storage section in configuration")

    if 'azure' not in config['storage']:
        # No azure storage, inject a fake url for now so if people want to use
        # the azure templates they know to come look here.
        return "https://AZURE NOT CONFIGURED, ADD A storage.azure section to " \
            "dcos-release.config.yaml to use the Azure templates"

    if 'download_url' not in config['storage']['azure']:
        raise RuntimeError("No download_url section in azure configuration")

    download_url = config['storage']['azure']['download_url']

    if not download_url.endswith('/'):
        raise RuntimeError("Azure download_url must end with a '/'")

    return download_url


def set_repository_metadata(repository, metadata, storage_providers, preferred_provider, config) -> None:
    metadata['repository_path'] = repository.path_prefix[:-1]
    metadata['repository_url'] = preferred_provider.url + repository.path_prefix[:-1]
    metadata['build_name'] = repository.path_channel_prefix[:-1]
    metadata['reproducible_artifact_path'] = repository.reproducible_artifact_path[:-1]
    metadata['storage_urls'] = {}
    for name, store in storage_providers.items():
        metadata['storage_urls'][name] = store.url

    if 'options' not in config:
        raise RuntimeError("No options section in configuration")

    if 'cloudformation_s3_url' not in config['options']:
        raise RuntimeError("No options.cloudformation_s3_url section in configuration")

    metadata['cloudformation_s3_url_full'] = config['options']['cloudformation_s3_url'] + \
        '/{}/cloudformation'.format(metadata['reproducible_artifact_path'])

    metadata['azure_download_url'] = get_azure_download_url(config)


def call_matching_arguments(function, arguments, allow_unused=False):
    signature = inspect.signature(function)
    arguments = copy.deepcopy(arguments)

    kwargs = {}

    for name, info in signature.parameters.items():
        if name in arguments:
            kwargs[name] = arguments[name]
            del arguments[name]

            continue

        if info.default is not inspect.Parameter.empty:
            kwargs[name] = info.default
            continue

        raise ConfigError("Need a value for {}".format(name))

    if not allow_unused and len(arguments) > 0:
        raise ConfigError("Unused configuration parameters {}".format(arguments.keys()))

    return function(**kwargs)


def get_storage_provider_factory(kind):
    # Get the module containing it (kind portion before `_`)
    if '_' not in kind:
        raise ConfigError("Storage kind must be of the form <provider>_<name>")
    parts = kind.split('_', 1)
    assert len(parts) == 2
    provider, name = parts

    try:
        module = importlib.import_module("release.storage." + provider)
    except ImportError:
        raise ConfigError("Couldn't load storage provider '{}'".format(provider))

    if name not in module.factories:
        raise ConfigError("Storage provider {} has no kind {}".format(provider, name))

    return module.factories[name]


def apply_storage_commands(storage_providers: dict, storage_commands: dict) -> None:
    assert storage_commands.keys() == {'stage1', 'stage2'}

    for stage in ['stage1', 'stage2']:
        commands = storage_commands[stage]
        for provider_name, provider in storage_providers.items():
            for artifact in commands:
                path = artifact['args']['destination_path']
                # If it is only supposed to be if the artifact does not exist, check for existence
                # and skip if it exists.
                if artifact['if_not_exists'] and provider.exists(path):
                    print("Store to", provider_name, "artifact", path, "skipped because it already exists")
                    continue
                print("Store to", provider_name, "artifact", path, "by method", artifact['method'])
                getattr(provider, artifact['method'])(**artifact['args'])


# Two stages of uploading artifacts. First puts all the artifacts into their places / uploads
# all the artifacts to all providers. The second makes the end user known / used urls have the
# correct artifacts.
# The split is because in order to use some artifacts (Such as the cloudformation template) other
# artifacts must already be in place. All those artifacts which must be in place get uploaded in
# upload artifacts. By having the two steps we guarantee that a user is never able to download
# something such as a cloudformation template which won't work.
class ReleaseManager():

    def _setup_storage(self, storage_config):
        self.__storage_providers = {}
        for name, options in storage_config.items():
            options = copy.deepcopy(options)
            if 'kind' not in options:
                raise ConfigError("Must set the config kind for storage {}".format(name))
            factory = get_storage_provider_factory(options['kind'])

            # Remove meta parameters
            del options['kind']
            read_only = options.get('read_only', False)
            if 'read_only' in options:
                del options['read_only']

            # Construct the storage, making sure all remaining configuration options
            # are used.
            storage = call_matching_arguments(factory, options)

            # If read only wrap in the read_only proxy
            if read_only:
                storage = release.storage.ReadOnlyProxy(storage)

            self.__storage_providers[name] = storage

    def __init__(self, config, noop):
        self._setup_storage(config.get('storage', dict()))
        self.__noop = noop
        self.__config = config

        preferred_name = config.get('options', dict()).get('preferred')
        if preferred_name:
            self.__preferred_provider = self.__storage_providers[preferred_name]
        else:
            self.__preferred_provider = None

    def get_metadata(self, src_channel):
        return from_json(self.__preferred_provider.fetch(src_channel + '/metadata.json').decode())

    def fetch_key_artifacts(self, metadata):
        assert metadata['reproducible_artifact_path'][-1] != '/'
        assert metadata['repository_path'][-1] != '/'

        def fetch_artifact(artifact):
            print("Fetching core artifact if it doesn't exist: ", artifact)
            if 'channel_path' in artifact:
                assert artifact['channel_path'][0] != '/'
                src_path = metadata['reproducible_artifact_path'] + '/' + artifact['channel_path']
                # TODO(cmaloney): This is very hacky but for now the only ones of these we have
                # are all bootstrap related... The actual local path needs to be better represented
                # in the metadata uploaded. The destination upload paths and the temporary local
                # paths need to be made identical.
                dest_path = artifact['channel_path']
                if artifact['channel_path'].endswith('complete.latest.json'):
                    dest_path = 'packages/cache/complete/' + dest_path
                else:
                    dest_path = 'packages/cache/bootstrap/' + dest_path
                self.__preferred_provider.download(src_path, dest_path)
                artifact['local_copy_from'] = src_path
                artifact['local_path'] = artifact['channel_path']
            if 'reproducible_path' in artifact:
                assert artifact['reproducible_path'][0] != '/'

                local_path = "packages/cache/" + artifact['reproducible_path']

                src_path = metadata['repository_path'] + '/' + artifact['reproducible_path']

                self.__preferred_provider.download_if_not_exist(src_path, local_path)
                artifact['local_copy_from'] = src_path
                artifact['local_path'] = local_path

        for artifact in metadata['core_artifacts']:
            fetch_artifact(artifact)

    def promote(self, src_channel, destination_repository, destination_channel):
        metadata = self.get_metadata(src_channel)

        # Can't run a release promotion with a different version of the scripts than the one that
        # created the release.
        assert metadata['commit'] == util.dcos_image_commit, "You must promote from a checkout of " \
            "the same commit when `release create` aws run. {}".format(util.dcos_image_commit)

        self.fetch_key_artifacts(metadata)

        repository = Repository(destination_repository, destination_channel, 'commit/{}'.format(metadata['commit']))
        set_repository_metadata(
            repository, metadata, self.__storage_providers, self.__preferred_provider, self.__config)
        assert 'tag' in metadata
        del metadata['channel_artifacts']

        metadata['channel_artifacts'] = make_channel_artifacts(metadata)

        storage_commands = repository.make_commands(metadata)
        self.apply_storage_commands(storage_commands)

        return metadata

    def create_installer(self, src_channel):
        assert not src_channel.startswith('/')
        metadata = self.get_metadata(src_channel)
        self.fetch_key_artifacts(metadata)
        del metadata['channel_artifacts']
        make_channel_artifacts(metadata)

        return metadata

    def create(self, repository_path, channel, tag, tree_variants):
        assert len(channel) > 0  # channel must be a non-empty string.

        assert ('options' in self.__config) and \
            ('cloudformation_s3_url' in self.__config['options']), \
            "Must configure a cloudformation_s3_url which gets embedded in the AWS CloudFormation" \
            " templates."

        # TOOD(cmaloney): Figure out why the cached version hasn't been working right
        # here from the TeamCity agents. For now hardcoding the non-cached s3 download locatoin.
        metadata = make_stable_artifacts(
            self.__config['options']['cloudformation_s3_url'] + '/' + repository_path, tree_variants)

        # Metadata should already have things like bootstrap_id in it.
        assert 'bootstrap_dict' in metadata
        assert 'complete_dict' in metadata
        assert 'commit' in metadata

        # Assert that each variant's bootstrap's active packages are included in its complete package list.
        # TODO(branden): Make the complete package list available in the installer (for
        # dcos_installer.backend.do_aws_cf_configure()) and move this assertion to make_bootstrap_artifacts().
        for info in metadata['all_completes'].values():
            bootstrap_active_packages = set(
                pkgpanda.util.load_json('packages/cache/bootstrap/{}.active.json'.format(info['bootstrap']))
            )
            assert bootstrap_active_packages <= set(info['packages'])

        repository = Repository(repository_path, channel, 'commit/{}'.format(metadata['commit']))
        set_repository_metadata(
            repository, metadata, self.__storage_providers, self.__preferred_provider, self.__config)
        metadata['tag'] = tag
        assert 'channel_artifacts' not in metadata

        metadata['channel_artifacts'] = make_channel_artifacts(metadata)

        storage_commands = repository.make_commands(metadata)
        self.apply_storage_commands(storage_commands)

        return metadata

    def apply_storage_commands(self, storage_commands):
        assert storage_commands.keys() == {'stage1', 'stage2'}

        if self.__noop:
            return

        with logger.scope("Uploading artifacts"):
            apply_storage_commands(self.__storage_providers, storage_commands)


_config = None


def main():
    parser = argparse.ArgumentParser(description='DC/OS Release Management Tool.')
    subparsers = parser.add_subparsers(title='commands')

    parser.add_argument(
        '--noop',
        action='store_true',
        help="Do not take any actions on the storage providers, just run the "
             "whole build, produce the list of actions than no-op.")

    parser.add_argument(
        '-c',
        '--config',
        help="YAML configuration file",
        default="dcos-release.config.yaml")

    # Moves the latest of a given release name to the given release name.
    promote = subparsers.add_parser('promote')
    promote.set_defaults(action='promote')
    promote.add_argument('source_channel')
    promote.add_argument('destination_repository')

    # Use to create a different 'channel' which shares a reproducible artifact store, but has
    # independent non-reproducible artifacts (ex: dcos_generate_config.sh). Makes it so we don't
    # have as much redundant copying when there are a ton of branches (ex: testing/, dev/).
    # Always appends to the given repository ({repository}/{channel}).
    promote.add_argument('--destination-channel', action='store', default=None)

    # Creates, uploads, and marks as latest.
    # The marking as latest is ideally atomic (At least all artifacts when they
    # are uploaded should never result in a state where things don't work).
    create = subparsers.add_parser('create')
    create.set_defaults(action='create')
    # Channel is always implicitly prefixed with `testing`, so artifacts appear at
    # `testing/{channel}`
    create.add_argument('channel')
    create.add_argument('tag')
    create.add_argument(
        "--tree-variant",
        action='append',
        help="Create a tree using the specified tree variant. Multiple --tree-variant parameters "
        "can be specified. Use 'default' for the default variant on Linux and 'windows' for the default "
        "variant on Windows.",
        required=True
    )

    # Utility for building just the installers, useful for installer dev work where you don't want
    # to build all of dcos-image locally, and don't care about uploading. Defaults noop to true.
    create_installer = subparsers.add_parser("create-installer")
    create_installer.set_defaults(action='create-installer')
    create_installer.set_defaults(noop=True)
    create_installer.add_argument('src_channel')

    # Parse the arguments and dispatch.
    options = parser.parse_args()
    if not hasattr(options, 'action'):
        parser.print_help()
        print("ERROR: Must use a subcommand")
        sys.exit(1)

    try:
        # TODO(cmaloney): HACK. This is so we can get to the config for aws and azure template
        # testing inside gen/build_deploy/{aws,azure}.py
        global _config
        config = load_config(options.config)
        _config = config
    except OSError as ex:
        print("ERROR: Failed to open release configuration file '{}': {}".format(options.config, ex))
        sys.exit(1)

    release_manager = ReleaseManager(config, options.noop)
    if options.action == 'promote':
        release_manager.promote(options.source_channel, options.destination_repository, options.destination_channel)
    elif options.action == 'create':
        variants = [None if variant == "default" else variant for variant in options.tree_variant]
        release_manager.create('testing', options.channel, options.tag, variants)
    elif options.action == 'create-installer':
        release_manager.create_installer(options.src_channel)
    else:
        raise ValueError("Unexpection options.action {}".format(options.action))


if __name__ == '__main__':
    main()
