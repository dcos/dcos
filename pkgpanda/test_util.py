import os
import tempfile
from subprocess import CalledProcessError

import pytest

import pkgpanda.util
from pkgpanda import UserManagement
from pkgpanda.exceptions import ValidationError

PathSeparator = '/'  # Currently same for both windows and linux. Constant may vary in near future by platform


def test_remove_file_pass():
    """
     Remove a known directory. Should succeed silently.
    """
    test_dir = tempfile.gettempdir() + PathSeparator + 'test'

    # Here we really don't care if there is a left over dir since we will be removing it
    # but we need to make sure there is one
    pkgpanda.util.make_directory(test_dir)
    assert os.path.isdir(test_dir)

    # Build the temporary test file with a random name
    fno, test_path = tempfile.mkstemp(dir=test_dir)
    os.close(fno)  # Close the reference so we don't have dangling file handles

    test_data = "Test Data\n"
    with open(test_path, "w") as f:
        f.write(test_data)

    pkgpanda.util.remove_file(test_path)
    assert not os.path.exists(test_path), 'Directory item not removed'

    pkgpanda.util.remove_directory(test_dir)
    assert not os.path.exists(test_dir)


def test_remove_file_fail():
    """
     Remove a non existant directory item. Should fail silently without exceptions.
    """
    test_dir = tempfile.gettempdir() + PathSeparator + 'remove_directory_fail'
    test_path = test_dir + PathSeparator + "A"

    # Make sure there is no left over directory
    pkgpanda.util.remove_directory(test_dir)
    assert not os.path.isdir(test_dir)

    # We will try to remove a non-existant file

    try:
        pkgpanda.util.remove_file(test_path)
    except Exception:
        assert False, "Unexpected exception when trying to delete non existant directory item. Should fail silently"

    assert not os.path.exists(test_path)


def test_make_directory_pass():
    """
       Create a known directory and verify. Postcondition: the directory should exist
    """
    test_dir = tempfile.gettempdir() + PathSeparator + 'make_directory_pass'

    # Make sure there is no left over directory
    pkgpanda.util.remove_directory(test_dir)
    assert not os.path.isdir(test_dir)

    # Make the directory and check for its existence as a dir
    pkgpanda.util.make_directory(test_dir)
    assert os.path.isdir(test_dir)

    # Cleanup
    pkgpanda.util.remove_directory(test_dir)


def test_make_directory_fail():
    """
       Attempt to create a directory with a null name. Postcondition: Should throw an OSError
    """
    test_dir = ""  # Lets make nothing...

    # Try to make the directory and check for its error
    try:
        pkgpanda.util.make_directory(test_dir)
    except OSError as e:
        assert e.errno == 2  # File not foundError
        return

    assert False, 'did not see expected OSError when trying to build unnamed directory'


def test_copy_file_pass():
    """
       Copy a file from a known directory to another known file path.
       Postcondition: The file should have been copied.
       The copy should contain the same contents as the original.
    """
    # Make sure we don't have the temp dirs and files left over
    test_src_dir = tempfile.gettempdir() + PathSeparator + 'test_src'
    test_dst_dir = tempfile.gettempdir() + PathSeparator + 'test_dst'
    pkgpanda.util.remove_directory(test_src_dir)
    pkgpanda.util.remove_directory(test_dst_dir)
    assert not os.path.isdir(test_src_dir)
    assert not os.path.isdir(test_dst_dir)

    # Build the dirs for copying to/from
    pkgpanda.util.make_directory(test_src_dir)
    pkgpanda.util.make_directory(test_dst_dir)

    # Build the source file
    fno, src_path = tempfile.mkstemp(dir=test_src_dir)
    os.close(fno)

    # Build the temporary dest file with a random name
    fno, dst_path = tempfile.mkstemp(dir=test_dst_dir)
    os.close(fno)  # Close the reference so we don't have dangling file handles

    test_data = "Test Data\n"
    with open(src_path, "w") as f:
        f.write(test_data)

    # copy the source file to the destination directory
    pkgpanda.util.copy_file(src_path, dst_path)

    lines = []
    with open(dst_path, "r") as f:
        lines = f.readlines()

    assert lines[0] == test_data


def test_file_fail():
    """
       Copy a file from a known directory to another known file path whose directory does not exist.
       Postcondition: Should throw a CalledProcessError or an OSError
    """
    # Make sure we don't have the temp dirs and files left over
    test_src_dir = tempfile.gettempdir() + PathSeparator + 'test_src'
    test_dst_dir = tempfile.gettempdir() + PathSeparator + 'test_dst'
    pkgpanda.util.remove_directory(test_src_dir)
    pkgpanda.util.remove_directory(test_dst_dir)
    assert not os.path.isdir(test_src_dir)
    assert not os.path.isdir(test_dst_dir)

    # Build the dirs for copying to/from
    pkgpanda.util.make_directory(test_src_dir)

    # Build the source file
    fno, src_path = tempfile.mkstemp(dir=test_src_dir)
    os.close(fno)

    dst_path = test_dst_dir + PathSeparator + os.path.basename(src_path)
    test_data = "Test Data\n"
    with open(src_path, "w") as f:
        f.write(test_data)

    # copy the source file to the destination directory
    try:
        pkgpanda.util.copy_file(src_path, dst_path)
    except CalledProcessError as e:
        return
    except OSError as e:
        return

    assert False, 'did not see expected OSError when trying to copy to non-existant directory item'


def test_copy_directory_pass():
    """
       Copy a directory of files from a known directory to another known file path whose directory does not exist.
       Postcondition: Should have recursively created the directories and files for the entire tree
    """
    # Make sure we don't have the temp dirs and files left over
    test_src_dir = tempfile.gettempdir() + PathSeparator + 'test_src'
    test_dst_dir = tempfile.gettempdir() + PathSeparator + 'test_dst'
    pkgpanda.util.remove_directory(test_src_dir)
    pkgpanda.util.remove_directory(test_dst_dir)
    assert not os.path.isdir(test_src_dir)
    assert not os.path.isdir(test_dst_dir)

    # Build the dirs for copying to/from
    pkgpanda.util.make_directory(test_src_dir)

    # Build the temporary source file with a random name
    fno, src_path = tempfile.mkstemp(dir=test_src_dir)
    os.close(fno)  # Close the reference so we don't have dangling file handles

    dst_path = test_dst_dir + PathSeparator + os.path.basename(src_path)

    test_data = "Test Data\n"
    with open(src_path, "w") as f:
        f.write(test_data)

    # copy the source file to the destination directory
    pkgpanda.util.copy_directory(test_src_dir, test_dst_dir)
    with open(dst_path, "r") as f:
        lines = f.readlines()

    assert lines[0] == test_data


def test_copy_directory_fail():
    """
       Attempt to copy a directory of files from a none existant directory to another
       known file path whose directory does not exist.
       Postcondition: We should get either a
    """
    # Make sure we don't have the temp dirs and files left over
    test_src_dir = tempfile.gettempdir() + PathSeparator + 'test_src'
    test_dst_dir = tempfile.gettempdir() + PathSeparator + 'test_dst'
    pkgpanda.util.remove_directory(test_src_dir)
    pkgpanda.util.remove_directory(test_dst_dir)
    assert not os.path.isdir(test_src_dir)
    assert not os.path.isdir(test_dst_dir)

    # try to copy the source file to the destination directory
    try:
        pkgpanda.util.copy_directory(test_src_dir, test_dst_dir)
    except CalledProcessError as e:
        return
    except OSError as e:
        return

    assert False, 'did not see expected OSError when trying to copy to non-existant directory tree'


def test_remove_directory():
    test_dir = tempfile.gettempdir() + PathSeparator + 'test'

    # Here we really don't care if there is a left over dir since we will be removing it
    # but we need to make sure there is one
    pkgpanda.util.make_directory(test_dir)
    assert os.path.isdir(test_dir)

    # Add some subdirectories and files
    pkgpanda.util.make_directory(test_dir + PathSeparator + 'A')

    # Build  a file
    fno, file_path = tempfile.mkstemp(dir=test_dir)
    os.close(fno)

    test_data = "Test Data\n"
    with open(file_path, "r+") as f:
        f.write(test_data)

    # Build  a file
    fno, file_path = tempfile.mkstemp(dir=test_dir + PathSeparator + 'A')
    os.close(fno)

    test_data = "Test Data 2\n"
    with open(file_path, "r+") as f:
        f.write(test_data)

    pkgpanda.util.remove_directory(test_dir)
    assert not os.path.exists(file_path)
    assert not os.path.isdir(test_dir + PathSeparator + 'A')
    assert not os.path.isdir(test_dir)


def test_islink(tmpdir):
    # Test file.
    temp_file = str(tmpdir.join("temp_file"))
    with open(temp_file, "w") as f:
        f.write("Test Data\n")
    assert not pkgpanda.util.islink(temp_file)

    temp_file_link = temp_file + "_link"
    pkgpanda.util.link_file(temp_file, temp_file_link)
    assert pkgpanda.util.islink(temp_file_link)

    # Test directory.
    temp_dir = str(tmpdir.join("temp_dir"))
    pkgpanda.util.make_directory(temp_dir)
    assert not pkgpanda.util.islink(temp_dir)

    temp_dir_link = temp_dir + "_link"
    pkgpanda.util.link_file(temp_dir, temp_dir_link)
    assert pkgpanda.util.islink(temp_dir_link)


def test_realpath(tmpdir):
    # Test file.
    temp_file = str(tmpdir.join("temp_file"))
    with open(temp_file, "w") as f:
        f.write("Test Data\n")
    assert pkgpanda.util.realpath(temp_file) == temp_file

    temp_file_link = temp_file + "_link"
    pkgpanda.util.link_file(temp_file, temp_file_link)
    assert pkgpanda.util.realpath(temp_file_link) == temp_file

    # Test directory.
    temp_dir = str(tmpdir.join("temp_dir"))
    pkgpanda.util.make_directory(temp_dir)
    assert pkgpanda.util.realpath(temp_dir) == temp_dir

    temp_dir_link = temp_dir + "_link"
    pkgpanda.util.link_file(temp_dir, temp_dir_link)
    assert pkgpanda.util.realpath(temp_dir_link) == temp_dir


def test_link_file(tmpdir):
    # Test file.
    temp_file = str(tmpdir.join("temp_file"))
    with open(temp_file, "w") as f:
        f.write("Test Data\n")

    temp_file_link = temp_file + "_link"
    pkgpanda.util.link_file(temp_file, temp_file_link)

    with open(temp_file_link, "r") as f:
        assert f.read() == "Test Data\n"

    # Test directory.
    temp_dir = str(tmpdir.join("temp_dir"))
    pkgpanda.util.make_directory(temp_dir)

    temp_dir_link = temp_dir + "_link"
    pkgpanda.util.link_file(temp_dir, temp_dir_link)

    temp_file = temp_dir + os.sep + "temp_file"
    with open(temp_file, "w") as f:
        f.write("Test Data\n")

    temp_file_link = temp_dir_link + os.sep + "temp_file"
    with open(temp_file_link, "r") as f:
        assert f.read() == "Test Data\n"


def test_variant_variations():
    assert pkgpanda.util.variant_str(None) == ''
    assert pkgpanda.util.variant_str('test') == 'test'

    assert pkgpanda.util.variant_object('') is None
    assert pkgpanda.util.variant_object('test') == 'test'

    assert pkgpanda.util.variant_name(None) == '<default>'
    assert pkgpanda.util.variant_name('test') == 'test'

    assert pkgpanda.util.variant_prefix(None) == ''
    assert pkgpanda.util.variant_prefix('test') == 'test.'


def test_validate_username():

    def good(name):
        UserManagement.validate_username(name)

    def bad(name):
        with pytest.raises(ValidationError):
            UserManagement.validate_username(name)

    good('dcos_mesos')
    good('dcos_a')
    good('dcos__')
    good('dcos_a_b_c')
    good('dcos_diagnostics')
    good('dcos_a1')
    good('dcos_1')

    bad('dcos')
    bad('d')
    bad('d_a')
    bad('foobar_asdf')
    bad('dcos_***')
    bad('dc/os_foobar')
    bad('dcos_foo:bar')
    bad('3dcos_foobar')
    bad('dcos3_foobar')


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="Windows does not have a root group")
def test_validate_group():
    # assuming linux distributions have `root` group.
    UserManagement.validate_group('root')

    with pytest.raises(ValidationError):
        UserManagement.validate_group('group-should-not-exist')


def test_split_by_token():
    split_by_token = pkgpanda.util.split_by_token

    # Token prefix and suffix must not be empty.
    with pytest.raises(ValueError):
        list(split_by_token('', ')', 'foo'))
    with pytest.raises(ValueError):
        list(split_by_token('(', '', 'foo'))
    with pytest.raises(ValueError):
        list(split_by_token('', '', 'foo'))

    # Empty string.
    assert list(split_by_token('{{ ', ' }}', '')) == [('', False)]

    # String with no tokens.
    assert list(split_by_token('{{ ', ' }}', 'no tokens')) == [('no tokens', False)]

    # String with one token.
    assert list(split_by_token('{{ ', ' }}', '{{ token_name }}')) == [('{{ token_name }}', True)]
    assert list(split_by_token('{{ ', ' }}', 'foo {{ token_name }}')) == [('foo ', False), ('{{ token_name }}', True)]
    assert list(split_by_token('{{ ', ' }}', '{{ token_name }} foo')) == [('{{ token_name }}', True), (' foo', False)]

    # String with multiple tokens.
    assert list(split_by_token('{{ ', ' }}', 'foo {{ token_a }} bar {{ token_b }} \n')) == [
        ('foo ', False), ('{{ token_a }}', True), (' bar ', False), ('{{ token_b }}', True), (' \n', False)
    ]

    # Token decoration is stripped when requested.
    assert list(split_by_token('[[', ']]', 'foo [[token_a]] bar[[token_b ]]', strip_token_decoration=True)) == [
        ('foo ', False), ('token_a', True), (' bar', False), ('token_b ', True)
    ]

    # Token prefix and suffix can be the same.
    assert list(split_by_token('||', '||', 'foo ||token_a|| bar ||token_b|| \n')) == [
        ('foo ', False), ('||token_a||', True), (' bar ', False), ('||token_b||', True), (' \n', False)
    ]
    assert list(split_by_token('||', '||', 'foo ||token_a|| bar ||token_b|| \n', strip_token_decoration=True)) == [
        ('foo ', False), ('token_a', True), (' bar ', False), ('token_b', True), (' \n', False)
    ]

    # Missing token suffix.
    with pytest.raises(Exception):
        list(split_by_token('(', ')', '(foo) (bar('))
    # Missing suffix for middle token.
    with pytest.raises(Exception):
        list(split_by_token('[[', ']]', '[[foo]] [[bar [[baz]]'))
    # Missing token prefix.
    with pytest.raises(Exception):
        list(split_by_token('[[', ']]', 'foo]] [[bar]]'))
    # Nested tokens.
    with pytest.raises(Exception):
        list(split_by_token('[[', ']]', '[[foo]] [[bar [[baz]] ]]'))

    # Docstring examples.
    assert list(split_by_token('{', '}', 'some text {token} some more text')) == [
        ('some text ', False), ('{token}', True), (' some more text', False)
    ]
    assert list(split_by_token('{', '}', 'some text {token} some more text', strip_token_decoration=True)) == [
        ('some text ', False), ('token', True), (' some more text', False)
    ]


def test_write_string(tmpdir):
    """
    `pkgpanda.util.write_string` writes or overwrites a file with permissions
    for User to read and write, Group to read and Other to read.

    Permissions of the given filename are preserved, or a new file is created
    with 0o644 permissions.

    This test was written to make current functionality regression-safe which
    is why no explanation is given for these particular permission
    requirements.

    Note that on Windows we do not have the same permissions so we skip those
    checks.
    """
    filename = os.path.join(str(tmpdir), 'foo_filename')
    pkgpanda.util.write_string(filename=filename, data='foo_contents')
    with open(filename) as f:
        assert f.read() == 'foo_contents'

    pkgpanda.util.write_string(filename=filename, data='foo_contents_2')
    with open(filename) as f:
        assert f.read() == 'foo_contents_2'
    if not pkgpanda.util.is_windows:
        st_mode = os.stat(filename).st_mode
        expected_permission = 0o644
        assert (st_mode & 0o777) == expected_permission

    if not pkgpanda.util.is_windows:
        os.chmod(filename, 0o777)
        pkgpanda.util.write_string(filename=filename, data='foo_contents_3')
        with open(filename) as f:
            assert f.read() == 'foo_contents_3'
        st_mode = os.stat(filename).st_mode
        expected_permission = 0o777
        assert (st_mode & 0o777) == expected_permission

