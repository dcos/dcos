import os
import stat
import tarfile
import tempfile

import pytest

import gen
import pkgpanda.util


def file_mode(filename: str) -> str:
    """Return a string containing the octal mode for filename."""
    return '{0:04o}'.format(stat.S_IMODE(os.stat(filename).st_mode))


def assert_package_contents(config: dict, package_contents_dir: str) -> None:
    """Raise an AssertionError if config does not match package_contents_dir."""
    # Assert all files in config are in package_contents_dir with the correct details.
    for file_info in config['package']:
        if file_info['path'].startswith('/'):
            file_path = package_contents_dir + file_info['path']
        else:
            file_path = package_contents_dir + '/' + file_info['path']

        assert os.path.exists(file_path)
        assert file_mode(file_path) == file_info.get('permissions', '0644')
        with open(file_path, encoding='utf-8') as f:
            assert f.read() == (file_info['content'] or '')

    # Assert all files in package_contents_dir are mentioned in config.
    config_files = set(info['path'] for info in config['package'])
    for root, _, files in os.walk(package_contents_dir):
        for filename in files:
            package_filename = os.path.join(root, filename)[len(package_contents_dir):]
            # The filename in config might leave out the leading slash.
            assert package_filename in config_files or package_filename[1:] in config_files


def assert_do_gen_package(config: dict) -> None:
    """Generate a package from config and raise an AssertionError if incorrect."""
    with tempfile.TemporaryDirectory() as tmpdir:
        package_filename = os.path.join(tmpdir, 'package.tar.xz')
        package_extract_dir = os.path.join(tmpdir, 'package')

        # Build and extract package.
        gen.do_gen_package(config, package_filename)
        os.makedirs(package_extract_dir)
        with tarfile.open(package_filename) as package_tarball:
            package_tarball.extractall(package_extract_dir)

        assert_package_contents(config, package_extract_dir)


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="test fails on Windows reason unknown")
def test_do_gen_package():
    assert_do_gen_package({'package': [
        {
            'path': '/etc/foo',
            'content': 'foo',
            'permissions': '0600',
        },
        {
            'path': '/bin/bar',
            'content': 'bar',
        },
        {
            'path': '/baz/qux/quux',
            'content': 'quux',
        },
        {
            'path': '/emptyfile1',
            'content': '',
        },
        {
            'path': '/emptyfile2',
            'content': None,
        },
    ]})

    # File paths may omit the leading slash.
    assert_do_gen_package({'package': [
        {
            'path': 'etc/foo',
            'content': 'foo',
        },
    ]})

    # File config may not contain unrecognized keys.
    with pytest.raises(Exception):
        assert_do_gen_package({'package': [
            {
                'path': '/etc/foo',
                'content': 'foo',
                'unrecognized_key': 'value',
            },
        ]})

    # File config must contain a path and content.
    with pytest.raises(Exception):
        assert_do_gen_package({'package': [
            {
                'path': '/etc/foo',
            },
        ]})
    with pytest.raises(Exception):
        assert_do_gen_package({'package': [
            {
                'content': 'foo',
            },
        ]})


def test_extract_files_containing_late_variables():
    regular_config_files = [
        {
            'path': '/foo',
            'content': 'foo',
        },
        {
            'path': '/bar',
            'content': 'bar',
        },
        {
            'path': '/empty',
            'content': None,
        },
    ]
    late_config_files = [
        {
            'path': '/baz',
            'content': gen.internals.LATE_BIND_PLACEHOLDER_START,
        },
        {
            'path': '/qux',
            'content': gen.internals.LATE_BIND_PLACEHOLDER_END,
        },
        {
            'path': '/quux',
            'content': '{}quux{}'.format(
                gen.internals.LATE_BIND_PLACEHOLDER_START,
                gen.internals.LATE_BIND_PLACEHOLDER_END,
            ),
        },
    ]
    assert (
        gen.extract_files_containing_late_variables(regular_config_files + late_config_files) ==
        (late_config_files, regular_config_files)
    )

    # Only content may contain late bind placeholders.
    with pytest.raises(Exception):
        gen.extract_files_containing_late_variables([
            {
                'path': gen.internals.LATE_BIND_PLACEHOLDER_START,
                'content': '',
            }
        ])
    with pytest.raises(Exception):
        gen.extract_files_containing_late_variables([
            {
                'path': '/foo',
                'content': '',
                'permissions': gen.internals.LATE_BIND_PLACEHOLDER_START,
            }
        ])


def test_validate_downstream_entry():
    # Valid entries.
    gen.validate_downstream_entry({
        'default': {
            'foo': 'foo',
        },
        'must': {
            'bar': 'bar',
        },
    })
    gen.validate_downstream_entry({
        'default': {
            'foo': 'foo',
        },
    })
    gen.validate_downstream_entry({
        'must': {
            'bar': 'bar',
        },
    })

    # dcos_version may not be redefined downstream.
    with pytest.raises(Exception):
        gen.validate_downstream_entry({
            'default': {
                'foo': 'foo',
            },
            'must': {
                'dcos_version': 'new_version',
            },
        })
    with pytest.raises(Exception):
        gen.validate_downstream_entry({
            'default': {
                'dcos_version': 'new_version',
            },
            'must': {
                'bar': 'bar',
            },
        })
