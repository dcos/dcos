import json
import os
from os import sep
from shutil import copytree
from subprocess import CalledProcessError, check_call, check_output

import pytest

import pkgpanda.build
import pkgpanda.build.cli
from pkgpanda.util import expect_fs, is_windows, remove_file


def get_tar_contents(filename, tmpdir):
    if is_windows:
        remove_tmp_file = False
        if filename.endswith(".tar.xz"):
            # We need to get 7z to expand the .xz into a tar first so we can look inside
            with tmpdir.as_cwd():
                check_output(["7z.exe", "x", filename])
            _, filename_file = os.path.split(filename)
            tar_filename, _ = os.path.splitext(filename_file)
            filename = tmpdir.join(tar_filename)
            remove_tmp_file = True
        # now we have the extracted .tar file in the temp directory, get the contents
        output = check_output(["7z.exe", "l", str(filename)]).decode().splitlines()
        if remove_tmp_file:
            remove_file(str(filename))
        # Strip first 17 lines and last 2 lines, then strip first 53 characters of each line
        return set([line[53:] for line in output[17:-2]])
    else:
        return set(check_output(["tar", "-tf", filename]).decode().splitlines())


def package(resource_dir, name, tmpdir):
    # Build once using command line interface
    pkg_dir = tmpdir.join(name)
    copytree(resource_dir, str(pkg_dir))
    with pkg_dir.as_cwd():
        if is_windows:
            check_call(["mkpanda", "--variant=windows"])
        else:
            check_call(["mkpanda", "--variant=default"])

    # Build once using programmatic interface
    pkg_dir_2 = str(tmpdir.join("api-build/" + name))
    copytree(resource_dir, pkg_dir_2)
    package_store = pkgpanda.build.PackageStore(str(tmpdir.join("api-build")), None)
    if is_windows:
        return pkgpanda.build.pkgpanda.build.build(package_store, name, "windows", True)
    else:
        return pkgpanda.build.pkgpanda.build.build(package_store, name, None, True)


def test_build(tmpdir):
    package("resources" + sep + "base", "base", tmpdir)
    # TODO(cmaloney): Check the package exists with the right contents.


def test_build_bad_sha1(tmpdir):
    package("resources" + sep + "base", "base", tmpdir)


def test_hash_build_script(tmpdir):
    # hashcheck1 is the base package we're comparing against.
    pkg_path1 = str(package("resources/buildhash/hashcheck1", "hashcheck", tmpdir.join("hashcheck1")))
    # hashcheck2 is identical to hashcheck1 other that a tweak to the build script.
    pkg_path2 = str(package("resources/buildhash/hashcheck2", "hashcheck", tmpdir.join("hashcheck2")))
    # hashcheck3 is identical to hashcheck1 in every way other than the directory name.
    pkg_path3 = str(package("resources/buildhash/hashcheck3", "hashcheck", tmpdir.join("hashcheck3")))
    assert os.path.basename(pkg_path1) == os.path.basename(pkg_path3)
    assert os.path.basename(pkg_path1) != os.path.basename(pkg_path2)


def test_url_extract_tar(tmpdir):
    package("resources" + sep + "url_extract-tar", "url_extract-tar", tmpdir)


def test_url_extract_zip(tmpdir):
    package("resources" + sep + "url_extract-zip", "url_extract-zip", tmpdir)


def test_single_source_with_extra(tmpdir):
    package("resources" + sep + "single_source_extra", "single_source_extra", tmpdir)

    # remove the built package tarball because that has a variable filename
    cache_dir = tmpdir.join("cache" + sep + "packages" + sep + "single_source_extra" + sep)
    packages = [str(x) for x in cache_dir.visit(fil="single_source_extra*.tar.xz")]
    assert len(packages) == 1, "should have built exactly one package: {}".format(packages)
    os.remove(packages[0])

    if is_windows:
        expect_fs(str(cache_dir), {
            "windows.latest": None,
            "single_source_extra": ["foo"]})
    else:
        expect_fs(str(cache_dir), {
            "latest": None,
            "single_source_extra": ["foo"]})


def test_bad_buildinfo(tmpdir):
    def tmp_pkg(name, buildinfo):
        if is_windows:
            buildfilename = "build.ps1"
        else:
            buildfilename = "build"
        pkg_dir = tmpdir.join(name)
        pkg_dir.ensure(dir=True)
        pkg_dir.join('buildinfo.json').write(json.dumps(buildinfo).encode())
        pkg_dir.join(buildfilename).ensure()
        with pytest.raises(pkgpanda.build.BuildError):
            package_store = pkgpanda.build.PackageStore(str(tmpdir), None)
            pkgpanda.build.build_package_variants(package_store, name, True)
            package(str(pkg_dir), name, tmpdir.join(buildfilename))

    if is_windows:
        tmp_pkg('unknown_field', {'user': 'dcos_user', 'docker': 'microsoft/windowsservercore:1803'})
        tmp_pkg('disallowed_field', {'name': 'disallowed_field', 'docker': 'microsoft/windowsservercore:1803'})
    else:
        tmp_pkg('unknown_field', {'user': 'dcos_user', 'docker': 'ubuntu:14.04.4'})
        tmp_pkg('disallowed_field', {'name': 'disallowed_field', 'docker': 'ubuntu:14.04.4'})


# TODO(cmaloney): Re-enable once we build a dcos-builder docker as part of this test. Currently the
# default docker is dcos-builder, and that isn't built here so these tests fail.
# def test_no_buildinfo(tmpdir):
#    package("resources/no_buildinfo", "no_buildinfo", tmpdir)


def test_restricted_services(tmpdir):
    with pytest.raises(CalledProcessError):
        package("resources-nonbootstrapable" + sep + "restricted_services", "restricted_services", tmpdir)


def test_single_source_corrupt(tmpdir):
    with pytest.raises(CalledProcessError):
        package("resources-nonbootstrapable" + sep + "single_source_corrupt", "single_source", tmpdir)

    # Check the corrupt file got moved to the right place
    expect_fs(str(tmpdir.join("cache" + sep + "packages" + sep + "single_source" + sep + "single_source")),
              ["foo.corrupt"])


def test_bootstrap(tmpdir):
    pkg_dir = tmpdir.join("bootstrap_test")
    copytree("resources/", str(pkg_dir))
    with pkg_dir.as_cwd():
        if is_windows:
            treeinfo = {
                'variants': {
                    'base': 'windows',
                    'single_source': 'windows',
                    'single_source_extra': 'windows',
                    'url_extract-tar': 'windows',
                    'url_extract-zip': 'windows',
                    'variant': 'downstream.windows',
                    'non_bootstrap': 'windows',
                    'non_bootstrap_variant': 'downstream.windows'
                }
            }
        else:
            treeinfo = {
                'variants': {
                    'variant': 'downstream',
                    'non_bootstrap_variant': 'downstream'
                }
            }
        # All packages in resources/ except non_bootstrap*
        treeinfo.update({
            'bootstrap_package_list': [
                'base',
                'single_source',
                'single_source_extra',
                'url_extract-tar',
                'url_extract-zip',
                'variant',
            ]
        })
        pkg_dir.join("treeinfo.json").write(json.dumps(treeinfo), ensure=True)
        check_call(["mkpanda", "tree", "--mkbootstrap"])
        cache_dir = str(pkg_dir.join("cache/bootstrap")) + "/"
        bootstrap_id = open(cache_dir + "bootstrap.latest", 'r').read().strip()
        bootstrap_files = get_tar_contents(cache_dir + bootstrap_id + ".bootstrap.tar.xz", tmpdir)

        # Seperate files that come from individual packages from those in the root directory
        package_files = dict()
        merged_files = set()
        for path in bootstrap_files:
            print("Processing: " + path)
            # Skip the packages folder itself
            if is_windows:
                packages_dir = "packages"
            else:
                packages_dir = "./packages/"
            if path == packages_dir:
                continue

            if is_windows:
                packages_dir = "packages\\"
            else:
                packages_dir = "./packages/"
            if not path.startswith(packages_dir):
                merged_files.add(path)
                continue

            # Figure out the package name, file inside the package
            path_parts = path.split(os.sep)
            print("path parts: {}".format(path_parts))
            if is_windows:
                # on windows first is 'package' hten package--name
                package_name = path_parts[1].split('--')[0]
            else:
                # on linux first path is '.', then 'package' then package--name
                package_name = path_parts[2].split('--')[0]
            print("Package name: " + package_name)
            if is_windows:
                file_path = os.sep.join(path_parts[2:])
            else:
                file_path = os.sep.join(path_parts[3:])
            print("file_path=" + file_path)
            file_set = package_files.get(package_name, set())

            # don't add the package directory / empty path.
            if len(file_path) == 0:
                continue
            file_set.add(file_path)
            package_files[package_name] = file_set

        # Check that the root has exactly the right set of files.
        if is_windows:
            expected_merged_files = {
                'active.buildinfo.full.json',
                'bootstrap',
                'environment.ps1',
                'environment.export.ps1',
                'active',
                'active\\base',
                'active\\url_extract-tar',
                'active\\url_extract-zip',
                'active\\variant',
                'active\\single_source',
                'active\\single_source_extra',
                'bin',
                'bin\\mesos-master',
                'etc',
                'etc\\dcos-service-configuration.json',
                'lib',
                'lib',
                'lib\\libmesos.so',
                'include'}
        else:
            expected_merged_files = {
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
        assert merged_files == expected_merged_files

        if is_windows:
            expected_package_files = {
                'url_extract-zip': {'buildinfo.full.json', 'pkginfo.json'},
                'url_extract-tar': {'pkginfo.json', 'buildinfo.full.json'},
                'single_source': {'pkginfo.json', 'buildinfo.full.json'},
                'single_source_extra': {'buildinfo.full.json', 'pkginfo.json'},
                'variant': {'buildinfo.full.json', 'pkginfo.json'},
                'base': {
                    'base',
                    'bin',
                    'dcos.target.wants',
                    'dcos.target.wants\\dcos-foo.service',
                    'version',
                    'buildinfo.full.json',
                    'bin\\mesos-master',
                    'pkginfo.json',
                    'lib',
                    'lib\\libmesos.so'}}
        else:
            expected_package_files = {
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
        assert package_files == expected_package_files
