import json
import os
from shutil import copytree
from subprocess import CalledProcessError, check_call, check_output

import pytest

import pkgpanda.build
import pkgpanda.build.cli
from pkgpanda.util import expect_fs, is_windows


def get_tar_contents(filename):
    return set(check_output(["tar", "-tf", filename]).decode().splitlines())


def package(resource_dir, name, tmpdir):
    # Build once using command line interface
    pkg_dir = tmpdir.join(name)
    copytree(resource_dir, str(pkg_dir))
    with pkg_dir.as_cwd():
        check_call(["mkpanda"])

    # Build once using programmatic interface
    pkg_dir_2 = str(tmpdir.join("api-build/" + name))
    copytree(resource_dir, pkg_dir_2)
    package_store = pkgpanda.build.PackageStore(str(tmpdir.join("api-build")), None)
    pkgpanda.build.build_package_variants(package_store, name, True)


@pytest.mark.skipif(is_windows, reason="Fails on windows, cause unknown")
def test_build(tmpdir):
    package("resources/base", "base", tmpdir)
    # TODO(cmaloney): Check the package exists with the right contents.


@pytest.mark.skipif(is_windows, reason="Fails on windows, cause unknown")
def test_build_bad_sha1(tmpdir):
    package("resources/base", "base", tmpdir)


@pytest.mark.skipif(is_windows, reason="Fails on windows, cause unknown")
def test_url_extract_tar(tmpdir):
    package("resources/url_extract-tar", "url_extract-tar", tmpdir)


@pytest.mark.skipif(is_windows, reason="Fails on windows, cause unknown")
def test_url_extract_zip(tmpdir):
    package("resources/url_extract-zip", "url_extract-zip", tmpdir)


@pytest.mark.skipif(is_windows, reason="Fails on windows, cause unknown")
def test_single_source_with_extra(tmpdir):
    package("resources/single_source_extra", "single_source_extra", tmpdir)

    # remove the built package tarball because that has a variable filename
    cache_dir = tmpdir.join("cache/packages/single_source_extra/")
    packages = [str(x) for x in cache_dir.visit(fil="single_source_extra*.tar.xz")]
    assert len(packages) == 1, "should have built exactly one package: {}".format(packages)
    os.remove(packages[0])

    expect_fs(str(cache_dir), {
        "latest": None,
        "single_source_extra": ["foo"]})


@pytest.mark.skipif(is_windows, reason="Fails on windows, cause unknown")
def test_bad_buildinfo(tmpdir):
    def tmp_pkg(name, buildinfo):
        pkg_dir = tmpdir.join(name)
        pkg_dir.ensure(dir=True)
        pkg_dir.join('buildinfo.json').write(json.dumps(buildinfo).encode())
        pkg_dir.join('build').ensure()
        with pytest.raises(pkgpanda.build.BuildError):
            package_store = pkgpanda.build.PackageStore(str(tmpdir), None)
            pkgpanda.build.build_package_variants(package_store, name, True)
            package(str(pkg_dir), name, tmpdir.join('build'))

    tmp_pkg('unknown_field', {'user': 'dcos_user', 'docker': 'ubuntu:14.04.4'})
    tmp_pkg('disallowed_field', {'name': 'disallowed_field', 'docker': 'ubuntu:14.04.4'})


# TODO(cmaloney): Re-enable once we build a dcos-builder docker as part of this test. Currently the
# default docker is dcos-builder, and that isn't built here so these tests fail.
# def test_no_buildinfo(tmpdir):
#    package("resources/no_buildinfo", "no_buildinfo", tmpdir)


def test_restricted_services(tmpdir):
    with pytest.raises(CalledProcessError):
        package("resources-nonbootstrapable/restricted_services", "restricted_services", tmpdir)


@pytest.mark.skipif(is_windows, reason="Fails on windows, cause unknown")
def test_single_source_corrupt(tmpdir):
    with pytest.raises(CalledProcessError):
        package("resources-nonbootstrapable/single_source_corrupt", "single_source", tmpdir)

    # Check the corrupt file got moved to the right place
    expect_fs(str(tmpdir.join("cache/packages/single_source/single_source")), ["foo.corrupt"])


@pytest.mark.skipif(is_windows, reason="Fails on windows, don't have necessary windows build scripts for this test")
def test_bootstrap(tmpdir):
    pkg_dir = tmpdir.join("bootstrap_test")
    copytree("resources/", str(pkg_dir))
    with pkg_dir.as_cwd():
        treeinfo = {
            'variants': {
                'variant': 'downstream',
                'non_bootstrap_variant': 'downstream',
            },
            # All packages in resources/ except non_bootstrap*
            'bootstrap_package_list': [
                'base',
                'single_source',
                'single_source_extra',
                'url_extract-tar',
                'url_extract-zip',
                'variant',
            ]
        }
        pkg_dir.join("treeinfo.json").write(json.dumps(treeinfo), ensure=True)
        check_call(["mkpanda", "tree", "--mkbootstrap"])
        cache_dir = str(pkg_dir.join("cache/bootstrap")) + "/"
        bootstrap_id = open(cache_dir + "bootstrap.latest", 'r').read().strip()
        bootstrap_files = get_tar_contents(cache_dir + bootstrap_id + ".bootstrap.tar.xz")

        # Seperate files that come from individual packages from those in the root directory
        package_files = dict()
        merged_files = set()
        for path in bootstrap_files:
            if not path.startswith("./packages/"):
                merged_files.add(path)
                continue

            # Skip the packages folder itself
            if path == './packages/':
                continue

            # Figure out the package name, file inside the package
            path_parts = path.split('/')
            package_name = path_parts[2].split('--')[0]
            file_path = '/'.join(path_parts[3:])
            file_set = package_files.get(package_name, set())

            # don't add the package directory / empty path.
            if len(file_path) == 0:
                continue
            file_set.add(file_path)
            package_files[package_name] = file_set

        # Check that the root has exactly the right set of files.
        assert merged_files == {
            './',
            './active.buildinfo.full.json',
            './bootstrap',
            './environment',
            './environment.export',
            './active/',
            './active/base',
            './active/url_extract-tar',
            './active/url_extract-zip',
            './active/variant',
            './active/single_source',
            './active/single_source_extra',
            './bin/',
            './bin/mesos-master',
            './etc/',
            './etc/dcos-service-configuration.json',
            './lib/',
            './lib/',
            './lib/libmesos.so',
            './include/'}

        assert package_files == {
            'url_extract-zip': {'pkginfo.json', 'buildinfo.full.json'},
            'url_extract-tar': {'pkginfo.json', 'buildinfo.full.json'},
            'single_source': {'pkginfo.json', 'buildinfo.full.json'},
            'single_source_extra': {'pkginfo.json', 'buildinfo.full.json'},
            'variant': {'pkginfo.json', 'buildinfo.full.json'},
            'base': {
                'base',
                'bin/',
                'dcos.target.wants/',
                'dcos.target.wants/dcos-foo.service',
                'version',
                'buildinfo.full.json',
                'bin/mesos-master',
                'pkginfo.json',
                'lib/',
                'lib/libmesos.so'}}
