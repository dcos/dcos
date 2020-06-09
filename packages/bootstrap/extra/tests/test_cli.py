import pytest

from dcos_internal_utils import cli


def test_telegraf_migration_empty(tmp_path):
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    src.mkdir()
    cli.migrate_containers(src, dst)
    assert not src.exists()
    assert dst.exists()
    assert not any(dst.iterdir())


def test_telegraf_migration_not_empty(tmp_path):
    file_contents = b'1234'
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    src.mkdir()
    file = src / 'file'
    file.write_bytes(file_contents)
    cli.migrate_containers(src, dst)
    assert not src.exists()
    assert dst.exists()
    file = dst / 'file'
    assert list(dst.iterdir()) == [file]
    assert file.read_bytes() == file_contents


def test_telegraf_migration_dst_exists_empty(tmp_path):
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    src.mkdir()
    dst.mkdir()
    cli.migrate_containers(src, dst)
    assert not src.exists()
    assert dst.exists()
    assert not any(dst.iterdir())


def test_telegraf_migration_dst_exists_not_empty(tmp_path):
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    src.mkdir()
    src_file = src / 'src_file'
    src_file.touch()
    dst.mkdir()
    dst_file = dst / 'dst_file'
    dst_file.touch()
    with pytest.raises(RuntimeError):
        cli.migrate_containers(src, dst)
    assert src.exists()
    assert src_file.exists()
    assert dst.exists()
    assert dst_file.exists()
