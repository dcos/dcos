import os
from shutil import copytree
from subprocess import CalledProcessError, check_call, check_output

import pytest

import pkgpanda.build
import pkgpanda.build.cli
from pkgpanda.util import expect_fs


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


def test_build(tmpdir):
    package("resources/base", "base", tmpdir)
    # TODO(cmaloney): Check the package exists with the right contents.


def test_build_bad_sha1(tmpdir):
    package("resources/base", "base", tmpdir)


def test_url_extract_tar(tmpdir):
    package("resources/url_extract-tar", "url_extract-tar", tmpdir)


def test_url_extract_zip(tmpdir):
    package("resources/url_extract-zip", "url_extract-zip", tmpdir)


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


# TODO(cmaloney): Re-enable once we build a dcos-builder docker as part of this test. Currently the
# default docker is dcos-builder, and that isn't built here so these tests fail.
# def test_no_buildinfo(tmpdir):
#    package("resources/no_buildinfo", "no_buildinfo", tmpdir)


def test_restricted_services(tmpdir):
    with pytest.raises(CalledProcessError):
        package("resources-nonbootstrapable/restricted_services", "restricted_services", tmpdir)


def test_single_source_corrupt(tmpdir):
    with pytest.raises(CalledProcessError):
        package("resources-nonbootstrapable/single_source_corrupt", "single_source", tmpdir)

    # Check the corrupt file got moved to the right place
    expect_fs(str(tmpdir.join("cache/packages/single_source/single_source")), ["foo.corrupt"])


def test_bootstrap(tmpdir):
    pkg_dir = tmpdir.join("bootstrap_test")
    copytree("resources/", str(pkg_dir))
    with pkg_dir.as_cwd():
        pkg_dir.join("treeinfo.json").write('', ensure=True)
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
        assert merged_files == set([
            './',
            './active.buildinfo.full.json',
            './bootstrap',
            './environment',
            './environment.export',
            './active/',
            './active/base',
            './active/url_extract-tar',
            './active/url_extract-zip',
            './active/single_source',
            './active/single_source_extra',
            # './active/no_buildinfo',
            './bin/',
            './bin/mesos-master',
            # './bin/no_buildinfo',
            './etc/',
            './lib/',
            './lib/libmesos.so',
            # './lib/no_buildinfo.so',
            './include/',
        ])
        # Check that each package has just the right set of files. All the right packages are present.
        assert package_files == {
            # 'no_buildinfo': set([
            #     'no_buildinfo',
            #     'version',
            #     'bin/ ',
            #     'buildinfo.full.json',
            #     'pkginfo.json',
            #     'lib/',
            #     'bin/',
            #     'lib/no_buildinfo.so']),
            'url_extract-zip': set(['pkginfo.json', 'buildinfo.full.json']),
            'url_extract-tar': set(['pkginfo.json', 'buildinfo.full.json']),
            'single_source': set(['pkginfo.json', 'buildinfo.full.json']),
            'single_source_extra': {'pkginfo.json', 'buildinfo.full.json'},
            'base': set([
                'base',
                'bin/',
                'dcos.target.wants/',
                'dcos.target.wants/dcos-foo.service',
                'version',
                'buildinfo.full.json',
                'bin/mesos-master',
                'pkginfo.json',
                'lib/',
                'lib/libmesos.so',
                ])
            }
