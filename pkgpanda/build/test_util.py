import pkgpanda.build


def test_hash_files_in_folder(tmpdir):
    hash_files_in_folder = pkgpanda.build.hash_files_in_folder

    with tmpdir.as_cwd():
        # Empty folder
        empty = tmpdir.join("test_empty")
        empty.ensure(dir=True)
        assert hash_files_in_folder(str("test_empty")) == {}

        # Empty subfolder
        empty.join("baz").ensure(dir=True)
        assert hash_files_in_folder(str("test_empty")) == {
            'baz': ""
        }

        # Empty folder in folder
        # empty.join("baz").join("bang").ensure(dir=True)
        # assert hash_files_in_folder(str("test_empty")) == {
        #     'baz/bang': ""
        # }
        empty.join("baz").join("bang").join("swish").ensure(dir=True)
        assert hash_files_in_folder(str("test_empty")) == {
            'baz/bang/swish': ""
        }

        simple = tmpdir.join("test_simple")
        simple.ensure(dir=True)
        simple.join("foo").write("foo contents")
        simple.join("bar").write("bar contents")
        assert hash_files_in_folder(str("test_simple")) == {
            'bar': '4acccb318abb44e0b8c4ba5e4e4a7fafa40243dd',
            'foo': '8a44735524900cdc94460b8999b581836535470e'
        }

        # Test having subdirectories
        baz = simple.join("baz")
        baz.ensure(dir=True)
        baz.join("foo").write("foo contents")
        baz.join("foo2").write("foo contents")

        assert hash_files_in_folder(str("test_simple")) == {
            'bar': '4acccb318abb44e0b8c4ba5e4e4a7fafa40243dd',
            'foo': '8a44735524900cdc94460b8999b581836535470e',
            'baz/foo': '8a44735524900cdc94460b8999b581836535470e',
            'baz/foo2': '8a44735524900cdc94460b8999b581836535470e'
        }

        # Test having subdirectories of subdirectories.
        bang = baz.join("bang")
        bang.ensure(dir=True)
        bang.join("bar").write("bar contents")
        bang.join("new").write("something new")

        assert hash_files_in_folder("test_simple") == {
            'bar': '4acccb318abb44e0b8c4ba5e4e4a7fafa40243dd',
            'foo': '8a44735524900cdc94460b8999b581836535470e',
            'baz/foo': '8a44735524900cdc94460b8999b581836535470e',
            'baz/foo2': '8a44735524900cdc94460b8999b581836535470e',
            'baz/bang/bar': '4acccb318abb44e0b8c4ba5e4e4a7fafa40243dd',
            'baz/bang/new': '15bc116ce980d703d62a16531b0ef5bb42fef91c'
        }

        swish = bang.join("swish")
        swish.ensure(dir=True)
        assert hash_files_in_folder("test_simple") == {
            'bar': '4acccb318abb44e0b8c4ba5e4e4a7fafa40243dd',
            'foo': '8a44735524900cdc94460b8999b581836535470e',
            'baz/foo': '8a44735524900cdc94460b8999b581836535470e',
            'baz/foo2': '8a44735524900cdc94460b8999b581836535470e',
            'baz/bang/bar': '4acccb318abb44e0b8c4ba5e4e4a7fafa40243dd',
            'baz/bang/new': '15bc116ce980d703d62a16531b0ef5bb42fef91c',
            'baz/bang/swish': ''
        }
        swish.join("swipe").write("swipe contents")
        assert hash_files_in_folder("test_simple") == {
            'bar': '4acccb318abb44e0b8c4ba5e4e4a7fafa40243dd',
            'foo': '8a44735524900cdc94460b8999b581836535470e',
            'baz/foo': '8a44735524900cdc94460b8999b581836535470e',
            'baz/foo2': '8a44735524900cdc94460b8999b581836535470e',
            'baz/bang/bar': '4acccb318abb44e0b8c4ba5e4e4a7fafa40243dd',
            'baz/bang/new': '15bc116ce980d703d62a16531b0ef5bb42fef91c',
            'baz/bang/swish/swipe': 'e855a8aca0e15c14144901428df7042798a622d6'
        }
