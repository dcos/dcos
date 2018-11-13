import json
import os
from os import sep
from shutil import copytree
from subprocess import CalledProcessError, check_call, check_output

import pytest

import pkgpanda.build
import pkgpanda.build.cli
from pkgpanda.util import expect_fs, is_windows


def contents_7z(out_7z):
    """Return the contents of an archive as listed by 7z's machine-readable verbose output.

    Returns a list of dictionaries containing the metadata for each file in the archive.
    out_7z is expected to be the string output of `7z.exe l -ba -slt`.
    """
    contents = []

    file_meta = {}
    for line in out_7z.splitlines():
        if line.strip() == "":
            # This is a break between sections in the output.
            # If the current file meta isn't empty, add it to contents and
            # begin defining a new file meta.
            if file_meta:
                contents.append(file_meta)
                file_meta = {}
            continue

        # Split the line to get its key and value.
        lineparts = line.split('=', maxsplit=1)
        if len(lineparts) != 2:
            raise Exception("unexpected or malformed line in 7z output")
        # Add the line's key and value to the file.
        file_meta[lineparts[0].strip()] = lineparts[1].strip()

    # Add the remainder.
    if file_meta:
        contents.append(file_meta)

    return contents


def get_tar_xz_contents(filename, tmpdir):
    """Lists the contents of a '*.tar.xz' file.

    On linux, This functions assumes that the archive was packaged as
        tar -cvf 'filename' .
    meaning that all of files in the archive have a './' prepended to them.

    On windows, with '7z', the './' is never present, so we manually add it in.
    """
    if is_windows:
        # On Windows, we need to tell 7z to expand the .xz into
        # a tar before we can list its contents.
        with tmpdir.as_cwd():
            check_output(["7z.exe", "x", filename])
        _, filename_file = os.path.split(filename)
        tar_filename, _ = os.path.splitext(filename_file)

        # Use the full path to the decompressed tar file to get its contents.
        filename = tmpdir.join(tar_filename)
        output = check_output(["7z.exe", "l", "-ba", "-slt", str(filename)]).decode()

        contents = {'.' + os.sep}
        for entry in contents_7z(output):
            path = '.' + os.sep + entry['Path']
            if entry.get('Folder') == '+' and not entry.get('Symbolic Link'):
                path += os.sep
            contents.add(path)

        return contents
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
        latestfile = "windows.latest"
    else:
        latestfile = "latest"

    expect_fs(str(cache_dir), {
        latestfile: None,
        "single_source_extra": ["foo"]})


def test_bad_buildinfo(tmpdir):
    def tmp_pkg(name, buildfile, buildinfofile, buildinfo):
        pkg_dir = tmpdir.join(name)
        pkg_dir.ensure(dir=True)
        pkg_dir.join(buildinfofile).write(json.dumps(buildinfo).encode())
        pkg_dir.join(buildfile).ensure()
        with pytest.raises(pkgpanda.build.BuildError):
            package_store = pkgpanda.build.PackageStore(str(tmpdir), None)
            pkgpanda.build.build_package_variants(package_store, name, True)
            package(str(pkg_dir), name, tmpdir.join(buildfile))

    if is_windows:
        buildfile = 'windows.build.ps1'
        buildinfofile = 'windows.buildinfo.json'
        buildinfo = {'docker': 'microsoft/windowsservercore:1803'}
    else:
        buildfile = 'build'
        buildinfofile = 'buildinfo.json'
        buildinfo = {'docker': 'ubuntu:14.04.4'}

    tmp_pkg('unknown_field', buildfile, buildinfofile, dict(buildinfo, **{'user': 'dcos_user'}))
    tmp_pkg('disallowed_field', buildfile, buildinfofile, dict(buildinfo, **{'name': 'disallowed_field'}))


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
        # All packages in resources/ except non_bootstrap*
        treeinfo = {
            'bootstrap_package_list': [
                'base',
                'single_source',
                'single_source_extra',
                'url_extract-tar',
                'url_extract-zip',
                'variant',
            ]
        }

        # Update treeinfo with per platform variant packages
        if is_windows:
            treeinfo.update({
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
            })
        else:
            treeinfo.update({
                'variants': {
                    'variant': 'downstream',
                    'non_bootstrap_variant': 'downstream'
                }
            })

        pkg_dir.join("treeinfo.json").write(json.dumps(treeinfo), ensure=True)
        check_call(["mkpanda", "tree", "--mkbootstrap"])
        cache_dir = str(pkg_dir.join("cache/bootstrap")) + "/"
        bootstrap_id = open(cache_dir + "bootstrap.latest", 'r').read().strip()
        bootstrap_files = get_tar_xz_contents(cache_dir + bootstrap_id + ".bootstrap.tar.xz", tmpdir)

        # Seperate files that come from individual packages from those in the root directory
        if is_windows:
            packages_dir = ".\\packages\\"
        else:
            packages_dir = "./packages/"

        package_files = dict()
        merged_files = set()
        for path in bootstrap_files:
            # Skip all files not in 'packages_dir'
            if not path.startswith(packages_dir):
                merged_files.add(path)
                continue

            # Skip the packages folder itself
            if path == packages_dir:
                continue

            # Figure out the package name, file inside the package
            path_parts = path.split(os.sep)
            package_name = path_parts[2].split('--')[0]
            file_path = os.sep.join(path_parts[3:])
            file_set = package_files.get(package_name, set())

            # don't add the package directory / empty path.
            if len(file_path) == 0:
                continue
            file_set.add(file_path)
            package_files[package_name] = file_set

        # Check that the root has exactly the right set of files.
        assert merged_files == {
            '.' + os.sep,
            '.' + os.sep + 'active' + os.sep,
            '.' + os.sep + 'active' + os.sep + 'base',
            '.' + os.sep + 'active' + os.sep + 'single_source',
            '.' + os.sep + 'active' + os.sep + 'single_source_extra',
            '.' + os.sep + 'active' + os.sep + 'url_extract-tar',
            '.' + os.sep + 'active' + os.sep + 'url_extract-zip',
            '.' + os.sep + 'active' + os.sep + 'variant',
            '.' + os.sep + 'bin' + os.sep,
            '.' + os.sep + 'bin' + os.sep + 'mesos-master',
            '.' + os.sep + 'etc' + os.sep,
            '.' + os.sep + 'etc' + os.sep + 'dcos-service-configuration.json',
            '.' + os.sep + 'lib' + os.sep,
            '.' + os.sep + 'lib' + os.sep + 'libmesos.so',
            '.' + os.sep + 'include' + os.sep,
            '.' + os.sep + 'active.buildinfo.full.json',
            '.' + os.sep + 'bootstrap',
            '.' + os.sep + 'environment' + (".ps1" if is_windows else ""),
            '.' + os.sep + 'environment.export' + (".ps1" if is_windows else "")}

        assert package_files == {
            'url_extract-zip': {'pkginfo.json', 'buildinfo.full.json'},
            'url_extract-tar': {'pkginfo.json', 'buildinfo.full.json'},
            'single_source': {'pkginfo.json', 'buildinfo.full.json'},
            'single_source_extra': {'pkginfo.json', 'buildinfo.full.json'},
            'variant': {'pkginfo.json', 'buildinfo.full.json'},
            'base': {
                'base',
                'bin' + os.sep,
                'bin' + os.sep + 'mesos-master',
                'dcos.target.wants' + os.sep,
                'dcos.target.wants' + os.sep + 'dcos-foo.service',
                'lib' + os.sep,
                'lib' + os.sep + 'libmesos.so',
                'buildinfo.full.json',
                'pkginfo.json',
                'version'}}
