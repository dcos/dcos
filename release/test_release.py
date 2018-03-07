import copy
import logging
import os
import subprocess
import uuid

import boto3
import pytest

import release
import release.storage.aws
from pkgpanda.build import BuildError
from pkgpanda.util import is_windows, make_directory, variant_prefix, write_json, write_string


def roundtrip_to_json(data, mid_state, new_end_state=None):
    assert release.to_json(data) == mid_state

    if new_end_state is not None:
        assert release.from_json(mid_state) == new_end_state
    else:
        assert release.from_json(mid_state) == data


def test_to_json():
    roundtrip_to_json('foo', '"foo"')
    roundtrip_to_json(['foo', 'bar'], '[\n  "foo",\n  "bar"\n]')
    roundtrip_to_json(('foo', 'bar'), '[\n  "foo",\n  "bar"\n]', ['foo', 'bar'])
    roundtrip_to_json({'foo': 'bar', 'baz': 'qux'}, '{\n  "baz": "qux",\n  "foo": "bar"\n}')

    # Sets aren't JSON serializable.
    with pytest.raises(TypeError):
        release.to_json({'foo', 'bar'})


def test_dict_to_json():
    # None in keys is converted to "null".
    roundtrip_to_json({None: 'foo'}, '{\n  "null": "foo"\n}')

    # Keys in resulting objects are sorted.
    roundtrip_to_json({None: 'baz', 'foo': 'bar'}, '{\n  "foo": "bar",\n  "null": "baz"\n}')

    # Nested dicts are processed too.
    roundtrip_to_json(
        {'foo': {'bar': 'baz', None: 'qux'}, None: 'quux'},
        '{\n  "foo": {\n    "bar": "baz",\n    "null": "qux"\n  },\n  "null": "quux"\n}')

    # Input isn't mutated.
    actual = {'foo': 'bar', None: {'baz': 'qux', None: 'quux'}}
    expected = copy.deepcopy(actual)
    release.to_json(actual)
    assert actual == expected


def test_strip_locals():
    # Raw pass through non-dictionary-like things
    assert release.strip_locals('foo') == 'foo'
    assert release.strip_locals(['a', 'b']) == ['a', 'b']

    # Dictionaries get all local_ keys removed
    assert release.strip_locals({'a': 'b', 'foo_local': 'foo'}) == {'a': 'b', 'foo_local': 'foo'}
    assert release.strip_locals({'local_a': 'foo'}) == {}
    assert release.strip_locals({'local_a': 'foo', None: 'foo'}) == {None: 'foo'}
    assert release.strip_locals({'a': 1, 'local_a': 3.4}) == {'a': 1}
    assert release.strip_locals({'local_a': 'foo', 'local_path': '/test', 'foobar': 'baz'}) == {'foobar': 'baz'}
    assert release.strip_locals({'local_a': 'foo', 'local_path': '/test'}) == {}

    # Test the recursive case, as well as that the source dictionary isn't modified.
    src_dict = {'a': {'local_a': 'foo'}, 'local_b': '/test', 'c': {'d': 'e', 'f': 'g'}}
    assert release.strip_locals(src_dict) == {'a': {}, 'c': {'d': 'e', 'f': 'g'}}
    assert src_dict == {'a': {'local_a': 'foo'}, 'local_b': '/test', 'c': {'d': 'e', 'f': 'g'}}

    # Test recursion with lists.
    # Dicts inside the list should be cleaned, but not the list itself.
    src_list = [{'a': {'local_a': 'foo'}, 'local_b': '/test', 'c': {'d': 'e', 'f': 'g'}}, 'local_h']
    assert release.strip_locals(src_list) == [{'a': {}, 'c': {'d': 'e', 'f': 'g'}}, 'local_h']
    assert src_list == [{'a': {'local_a': 'foo'}, 'local_b': '/test', 'c': {'d': 'e', 'f': 'g'}}, 'local_h']


def exercise_storage_provider(tmpdir, name, config):
    store = release.call_matching_arguments(release.get_storage_provider_factory(name), config, True)

    # Make a uniquely named test storage location, and try to upload / copy files
    # inside that location.
    test_id = uuid.uuid4().hex
    test_base_path = 'dcos-image-test-tmp/{}'.format(test_id)

    # We want to always disable caching and set content-type so that things work
    # right when debugging the tests.
    upload_extra_args = {
        'no_cache': True,
        'content_type': 'text/plain; charset=utf-8'
    }

    # Test we're starting with an empty test_base_path
    assert store.list_recursive(test_base_path) == set()

    # TODO(cmaloney): Add a test that uses different caching, content-type,
    # and checks that the caching of the url download location works properly
    # as well as the properties get carried through copies.

    assert store.url.endswith('/')

    def curl_fetch(path):
        return subprocess.check_output([
            'curl',
            '--fail',
            '--location',
            '--silent',
            '--show-error',
            '--verbose',
            store.url + path])

    def get_path(path):
        assert not path.startswith('/')
        return test_base_path + '/' + path

    def check_file(path, contents):
        # The store should be internally consistent / API return it exists now.
        assert store.exists(path)

        # We should be able to use the native fetching method.
        assert store.fetch(path) == contents

        # Other programs should be able to fetch with curl.
        assert curl_fetch(path) == contents

    def make_content(name):
        return (name + " " + uuid.uuid4().hex).encode()

    try:
        # Test uploading bytes.
        upload_bytes = make_content("upload_bytes")
        upload_bytes_path = get_path('upload_bytes.txt')

        # Check if exists on non-existent object works
        assert not store.exists(upload_bytes_path)

        store.upload(
            upload_bytes_path,
            blob=upload_bytes,
            **upload_extra_args)
        check_file(upload_bytes_path, upload_bytes)

        # Test uploading the same bytes to a non-existent subdirectory of a subdirectory
        upload_bytes_dir_path = get_path("dir1/bar/upload_bytes2.txt")
        store.upload(
            upload_bytes_dir_path,
            blob=upload_bytes,
            **upload_extra_args)

        # Test uploading a local file.
        upload_file = make_content("upload_file")
        upload_file_path = get_path('upload_file.txt')
        upload_file_local = tmpdir.join('upload_file.txt')
        upload_file_local.write(upload_file)
        store.upload(
            upload_file_path,
            local_path=str(upload_file_local),
            **upload_extra_args)
        check_file(upload_file_path, upload_file)

        # Test copying uploaded bytes.
        copy_dest_path = get_path('copy_file.txt')
        store.copy(upload_bytes_path, copy_dest_path)
        check_file(copy_dest_path, upload_bytes)

        # Test copying an uploaded file to a subdirectory.
        copy_dest_path = get_path('new_dir/copy_path.txt')
        store.copy(upload_file_path, copy_dest_path)
        check_file(copy_dest_path, upload_file)

        # Check that listing all the files in the storage provider gives the list of
        # files we've uploaded / checked and only that list of files.
        assert store.list_recursive(test_base_path) == {
            get_path('upload_file.txt'),
            get_path('upload_bytes.txt'),
            get_path('dir1/bar/upload_bytes2.txt'),
            get_path('new_dir/copy_path.txt'),
            get_path('copy_file.txt')
        }

        # Check that cleanup removes everything
        store.remove_recursive(test_base_path)
        assert store.list_recursive(test_base_path) == set()
    finally:
        # Cleanup temp directory in storage provider as best as possible.
        store.remove_recursive(test_base_path)


# TODO(cmaloney): Add skipping when not run under CI with the environment variables
# So devs without the variables don't see expected failures https://pytest.org/latest/skipping.html
def test_storage_provider_azure(release_config_azure, tmpdir):
    exercise_storage_provider(tmpdir, 'azure_block_blob', release_config_azure)


# TODO(cmaloney): Add skipping when not run under CI with the environment variables
# So devs without the variables don't see expected failures https://pytest.org/latest/skipping.html
def test_storage_provider_aws(release_config_aws, tmpdir):
    s3 = boto3.session.Session().resource('s3')
    bucket = release_config_aws['bucket']
    s3_bucket = s3.Bucket(bucket)
    assert s3_bucket in s3.buckets.all(), (
        "Bucket '{}' must exist with full write access to AWS testing account and created objects must be globally "
        "downloadable from: {}").format(bucket, release_config_aws['download_url'])

    exercise_storage_provider(tmpdir, 'aws_s3', release_config_aws)


@pytest.mark.skipif(is_windows, reason="Fails on windows, cause unknown")
def test_storage_provider_local(tmpdir):
    work_dir = tmpdir.mkdir("work")
    repo_dir = tmpdir.mkdir("repository")
    exercise_storage_provider(work_dir, 'local_path', {'path': str(repo_dir)})


copy_make_commands_result = {'stage1': [
    {
        'if_not_exists': True,
        'args': {
            'source_path': '/test_source_repo/1.html',
            'destination_path': 'stable/1.html'},
        'method': 'copy'},
    {
        'if_not_exists': True,
        'args': {
            'source_path': '/test_source_repo/3.html',
            'destination_path': 'stable/3.html'},
        'method': 'copy'},
    {
        'if_not_exists': False,
        'args': {
            'source_path': 'stable/3.html',
            'destination_path': 'stable/commit/testing_commit_2/3.html'},
        'method': 'copy'},
    {
        'if_not_exists': True,
        'args': {
            'source_path': '/test_source_repo/3.json',
            'destination_path': 'stable/3.json'},
        'method': 'copy'},
    {
        'if_not_exists': False,
        'args': {
            'source_path': 'stable/3.json',
            'destination_path': 'stable/commit/testing_commit_2/3.json'},
        'method': 'copy'},
    {
        'if_not_exists': False,
        'args': {
            'no_cache': True,
            'destination_path': 'stable/commit/testing_commit_2/2.html',
            'blob': b'2'},
        'method': 'upload'},
    {
        'if_not_exists': False,
        'args': {
            'no_cache': True,
            'destination_path': 'stable/commit/testing_commit_2/cf.json',
            'blob': b'{"a": "b"}',
            'content_type': 'application/json'},
        'method': 'upload'},
    {
        'if_not_exists': True,
        'args': {
            'no_cache': False,
            'destination_path': 'stable/some_big_hash.txt',
            'blob': b'hashy'},
        'method': 'upload'},
    {
        'if_not_exists': False,
        'args': {
            'no_cache': True,
            'destination_path': 'stable/commit/testing_commit_2/metadata.json',
            'blob': b'{\n  "channel_artifacts": [\n    {\n      "channel_path": "2.html"\n    },\n    {\n      "channel_path": "cf.json",\n      "content_type": "application/json"\n    },\n    {\n      "reproducible_path": "some_big_hash.txt"\n    }\n  ],\n  "core_artifacts": [\n    {\n      "reproducible_path": "1.html"\n    },\n    {\n      "channel_path": "3.html",\n      "content_type": "text/html",\n      "reproducible_path": "3.html"\n    },\n    {\n      "channel_path": "3.json",\n      "content_type": "application/json",\n      "reproducible_path": "3.json"\n    }\n  ],\n  "foo": "bar"\n}',  # noqa
            'content_type': 'application/json; charset=utf-8'},
        'method': 'upload'}
    ],
    'stage2': [{
        'if_not_exists': False,
        'args': {
            'source_path': 'stable/3.html',
            'destination_path': 'stable/3.html'},
        'method': 'copy'},
    {
        'if_not_exists': False,
        'args': {
            'source_path': 'stable/3.json',
            'destination_path': 'stable/3.json'},
        'method': 'copy'},
    {
        'if_not_exists': False,
        'args': {
            'source_path': 'stable/commit/testing_commit_2/2.html',
            'destination_path': 'stable/2.html'},
        'method': 'copy'},
    {
        'if_not_exists': False,
        'args': {
            'source_path': 'stable/commit/testing_commit_2/cf.json',
            'destination_path': 'stable/cf.json'},
        'method': 'copy'},
    {
        'if_not_exists': False,
        'args': {
            'source_path': 'stable/commit/testing_commit_2/metadata.json',
            'destination_path': 'stable/metadata.json'},
        'method': 'copy'}
    ]}

upload_make_command_results = {
    'stage2': [{
        'args': {
            'source_path': 'stable/commit/testing_commit_2/metadata.json',
            'destination_path': 'stable/metadata.json'},
            'method': 'copy',
            'if_not_exists': False}],
    'stage1': [{
        'args': {
            'no_cache': False,
            'destination_path':
            'stable/foo',
            'blob': b'foo'},
        'method': 'upload',
        'if_not_exists': True},
    {
        'args': {
            'no_cache': True,
            'destination_path': 'stable/commit/testing_commit_2/metadata.json',
            'blob': b'{\n  "channel_artifacts": [],\n  "core_artifacts": [\n    {\n      "reproducible_path": "foo"\n    }\n  ]\n}', 'content_type': 'application/json; charset=utf-8'},  # noqa
        'method': 'upload',
        'if_not_exists': False}
    ]}


def exercise_make_commands(repository):
    # Run make_commands on multiple different artifact
    # lists, make sure the output artifact list are what is expected given the
    # channel_prefix, channel_commit_path, channel_path, and repository_path
    # members.

    # TODO(cmaloney): Rather than one big make_commands test each different
    # artifact separately to make test failures more understandable, extending
    # as changes happen easier.
    # A list of artifacts that includes every attribute an artifact can have
    reproducible_artifacts = [
        {
            'reproducible_path': '1.html',
            'local_content': '1',
            'local_copy_from': '/test_source_repo/1.html'
        },
        {
            'reproducible_path': '3.html',
            'channel_path': '3.html',
            'local_content': '3',
            'content_type': 'text/html',
            'local_copy_from': '/test_source_repo/3.html'
        },
        {
            'reproducible_path': '3.json',
            'channel_path': '3.json',
            'local_path': '/test/foo.json',
            'content_type': 'application/json',
            'local_copy_from': '/test_source_repo/3.json'
        },
    ]

    channel_artifacts = [
        {
            'channel_path': '2.html',
            'local_content': '2'
        },
        {
            'channel_path': 'cf.json',
            'local_content': '{"a": "b"}',
            'content_type': 'application/json'
        },
        {
            'reproducible_path': 'some_big_hash.txt',
            'local_content': 'hashy',
        }
    ]

    metadata = {
        'foo': 'bar',
        'core_artifacts': reproducible_artifacts,
        'channel_artifacts': channel_artifacts
    }

    assert repository.make_commands(metadata) == copy_make_commands_result

    upload_could_copy_artifacts = [{
        'reproducible_path': 'foo',
        'local_content': 'foo'}]

    # Test a single simple artifact which should hit the upload logic rather than copy
    simple_artifacts = {'core_artifacts': upload_could_copy_artifacts, 'channel_artifacts': []}
    assert repository.make_commands(simple_artifacts) == upload_make_command_results


def test_repository():
    # Must specify a repository path
    with pytest.raises(ValueError):
        release.Repository("", None, "commit/testing_commit")

    # For an empty channel name, use None
    with pytest.raises(AssertionError):
        release.Repository("foo", "", "commit/testing_commit")

    # Repository path with no channel (Like we'd do for a stable or EA release).
    no_channel = release.Repository("stable", None, "commit/testing_commit_2")
    assert no_channel.channel_prefix == ''
    assert no_channel.reproducible_artifact_path + 'foo' == 'stable/commit/testing_commit_2/foo'
    assert no_channel.path_channel_prefix + 'bar' == 'stable/bar'
    assert no_channel.path_prefix + "a/baz--foo.tar.xz" == 'stable/a/baz--foo.tar.xz'
    exercise_make_commands(no_channel)

    # Repository path with a channel (Like we do for PRs)
    with_channel = release.Repository("testing", "pull/283", "commit/testing_commit_3")
    assert with_channel.channel_prefix == 'pull/283/'
    assert with_channel.reproducible_artifact_path + "foo" == 'testing/pull/283/commit/testing_commit_3/foo'
    assert with_channel.path_channel_prefix + "bar" == 'testing/pull/283/bar'
    assert with_channel.path_prefix + "a/baz--foo.tar.xz" == 'testing/a/baz--foo.tar.xz'
    # TODO(cmaloney): Exercise make_commands with a channel.


def test_get_gen_package_artifact(tmpdir):
    assert release.get_gen_package_artifact('foo--test') == {
        'reproducible_path': 'packages/foo/foo--test.tar.xz',
        'local_path': 'packages/foo/foo--test.tar.xz'
    }


def test_get_package_artifact(tmpdir):
    assert release.get_package_artifact('foo--test') == {
        'reproducible_path': 'packages/foo/foo--test.tar.xz',
        'local_path': 'packages/cache/packages/foo/foo--test.tar.xz'
    }


def mock_do_build_packages(cache_repository_url, tree_variants):
    make_directory('packages/cache/bootstrap')
    write_string("packages/cache/bootstrap/bootstrap_id.bootstrap.tar.xz", "bootstrap_contents")
    write_json("packages/cache/bootstrap/bootstrap_id.active.json", ['a--b', 'c--d'])
    write_string("packages/cache/bootstrap/bootstrap.latest", "bootstrap_id")
    write_string("packages/cache/bootstrap/installer.bootstrap.latest", "installer_bootstrap_id")
    write_json("packages/cache/bootstrap/installer_bootstrap_id.active.json", ['c--d', 'e--f'])
    write_string("packages/cache/bootstrap/downstream.installer.bootstrap.latest", "downstream_installer_bootstrap_id")
    write_json("packages/cache/bootstrap/downstream_installer_bootstrap_id.active.json", [])

    make_directory('packages/cache/complete')
    write_json(
        "packages/cache/complete/complete.latest.json",
        {'bootstrap': 'bootstrap_id', 'packages': ['a--b', 'c--d']})
    write_json(
        "packages/cache/complete/installer.complete.latest.json",
        {'bootstrap': 'installer_bootstrap_id', 'packages': ['c--d', 'e--f']})
    write_json(
        "packages/cache/complete/downstream.installer.complete.latest.json",
        {'bootstrap': 'installer_bootstrap_id', 'packages': []})

    return {
        None: {"bootstrap": "bootstrap_id", "packages": ["a--b", "c--d"]},
        "installer": {"bootstrap": "installer_bootstrap_id", "packages": ["c--d", "e--f"]},
        "downstream.installer": {"bootstrap": "downstream_installer_bootstrap_id", "packages": []}
    }


stable_artifacts_metadata = {
    'commit': 'commit_sha1',
    'core_artifacts': [
        {'local_path': 'packages/cache/bootstrap/bootstrap_id.bootstrap.tar.xz',
            'reproducible_path': 'bootstrap/bootstrap_id.bootstrap.tar.xz'},
        {'local_path': 'packages/cache/bootstrap/bootstrap_id.active.json',
            'reproducible_path': 'bootstrap/bootstrap_id.active.json'},
        {'local_path': 'packages/cache/bootstrap/bootstrap.latest',
            'channel_path': 'bootstrap.latest'},
        {'local_path': 'packages/cache/complete/complete.latest.json',
         'channel_path': 'complete.latest.json'},
        {'local_path': 'packages/cache/packages/a/a--b.tar.xz',
            'reproducible_path': 'packages/a/a--b.tar.xz'},
        {'local_path': 'packages/cache/packages/c/c--d.tar.xz',
            'reproducible_path': 'packages/c/c--d.tar.xz'},
        {'local_path': 'packages/cache/bootstrap/downstream_installer_bootstrap_id.bootstrap.tar.xz',
         'reproducible_path': 'bootstrap/downstream_installer_bootstrap_id.bootstrap.tar.xz'},
        {'local_path': 'packages/cache/bootstrap/downstream_installer_bootstrap_id.active.json',
         'reproducible_path': 'bootstrap/downstream_installer_bootstrap_id.active.json'},
        {'channel_path': 'downstream.installer.bootstrap.latest',
         'local_path': 'packages/cache/bootstrap/downstream.installer.bootstrap.latest'},
        {'local_path': 'packages/cache/complete/downstream.installer.complete.latest.json',
         'channel_path': 'downstream.installer.complete.latest.json'},
        {'local_path': 'packages/cache/bootstrap/installer_bootstrap_id.bootstrap.tar.xz',
            'reproducible_path': 'bootstrap/installer_bootstrap_id.bootstrap.tar.xz'},
        {'local_path': 'packages/cache/bootstrap/installer_bootstrap_id.active.json',
            'reproducible_path': 'bootstrap/installer_bootstrap_id.active.json'},
        {'local_path': 'packages/cache/bootstrap/installer.bootstrap.latest',
            'channel_path': 'installer.bootstrap.latest'},
        {'local_path': 'packages/cache/complete/installer.complete.latest.json',
         'channel_path': 'installer.complete.latest.json'},
        {'local_path': 'packages/cache/packages/e/e--f.tar.xz',
            'reproducible_path': 'packages/e/e--f.tar.xz'},
    ],
    'packages': ['a--b', 'c--d', 'e--f'],
    'bootstrap_dict': {None: "bootstrap_id"},
    'all_bootstraps': {
        None: "bootstrap_id",
        "installer": "installer_bootstrap_id",
        "downstream.installer": "downstream_installer_bootstrap_id"},
    'complete_dict': {
        None: {
            'bootstrap': 'bootstrap_id',
            'packages': ['a--b', 'c--d']}
    },
    'all_completes': {
        None: {
            'bootstrap': 'bootstrap_id',
            'packages': ['a--b', 'c--d']},
        'installer': {
            'bootstrap': 'installer_bootstrap_id',
            'packages': ['c--d', 'e--f']},
        'downstream.installer': {
            'bootstrap': 'downstream_installer_bootstrap_id',
            'packages': []}
    }
}


def mock_failed_build_packages(cache_repository_url, tree_variants):
    raise BuildError('This build failed!')


# TODO(cmaloney): Add test for do_build_packages returning multiple bootstraps
# containing overlapping
def test_make_stable_artifacts(monkeypatch, tmpdir):
    monkeypatch.setattr("release.do_build_packages", mock_do_build_packages)
    monkeypatch.setattr("gen.build_deploy.util.dcos_image_commit", "commit_sha1")

    with tmpdir.as_cwd():
        metadata = release.make_stable_artifacts("http://test", [None])
        assert metadata == stable_artifacts_metadata

    # Check that a BuildError is propogated
    monkeypatch.setattr("release.do_build_packages", mock_failed_build_packages)
    with pytest.raises(BuildError):
        release.make_stable_artifacts("http://test", [None])


# NOTE: Implicitly tests all gen.build_deploy do_create functions since it calls them.
# TODO(cmaloney): Test make_channel_artifacts, module do_create functions
def mock_make_installer_docker(variant, bootstrap_id, installer_bootstrap_id):
    return "dcos_generate_config." + variant_prefix(variant) + "sh"


def mock_get_cf_s3_url():
    return "http://mock_cf_s3_url"


def mock_get_azure_download_url():
    return "http://mock_azure_download_url"


def mock_make_tar(result_filename, folder):
    # Ensure the file exists.
    with open(result_filename, 'a'):
        pass


# Test that the do_create functions for each provider output data in the right
# shape.
def test_make_channel_artifacts(monkeypatch, release_config_aws):
    logging.basicConfig(level=logging.DEBUG)
    monkeypatch.setattr('gen.build_deploy.bash.make_installer_docker', mock_make_installer_docker)
    monkeypatch.setattr('pkgpanda.util.make_tar.__code__', mock_make_tar.__code__)

    metadata = {
        'commit': 'sha-1',
        'tag': 'test_tag',
        'bootstrap_dict': {
            None: 'bootstrap_id',
            'downstream': 'downstream_bootstrap_id'
        },
        'all_bootstraps': {
            None: 'bootstrap_id',
            'downstream': 'downstream_bootstrap_id',
            'installer': 'installer_bootstrap_id',
            'downstream.installer': 'downstream_installer_bootstrap_id'
        },
        'complete_dict': {
            None: {
                'bootstrap': 'bootstrap_id',
                'packages': ['package--version'],
            },
            'downstream': {
                'bootstrap': 'downstream_bootstrap_id',
                'packages': ['downstream-package--version'],
            },
        },
        'all_completes': {
            None: {
                'bootstrap': 'bootstrap_id',
                'packages': ['package--version'],
            },
            'downstream': {
                'bootstrap': 'downstream_bootstrap_id',
                'packages': ['downstream-package--version'],
            },
            'installer': {
                'bootstrap': 'installer_bootstrap_id',
                'packages': ['installer-package--version'],
            },
            'downstream.installer': {
                'bootstrap': 'downstream_installer_bootstrap_id',
                'packages': ['downstream-installer-package--version'],
            },
        },
        'build_name': 'r_path/channel',
        'reproducible_artifact_path': 'r_path/channel/commit/sha-1',
        'repository_path': 'r_path',
        'storage_urls': {
            'aws': 'https://aws.example.com/',
            'azure': 'https://azure.example.com/'
        },
        'repository_url': 'https://aws.example.com/r_path',
        'cloudformation_s3_url_full': 'https://s3.foobar.com/biz/r_path/channel/commit/sha-1',
        'azure_download_url': 'https://azure.example.com'
    }

    channel_artifacts = release.make_channel_artifacts(metadata)

    # Validate the artifacts are vaguely useful
    for artifact in channel_artifacts:
        assert 'local_path' in artifact or 'local_content' in artifact
        assert 'reproducible_path' in artifact or 'channel_path' in artifact


def test_make_abs():
    assert release.make_abs("/foo") == '/foo'
    assert release.make_abs("foo") == os.getcwd() + '/foo'


# TODO(cmaloney): Test do_build_packages?

# TODO(cmaloney): Test make_genconf_docker

# TODO(cmaloney): Test build_genconfs

# TODO(cmaloney): Test ReleaseManager.create() followed by ReleaseManager.promote() followed by a second promote.
