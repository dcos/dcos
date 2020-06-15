import pytest

from dcos_internal_utils import cli


def test_telegraf_no_legacy(tmp_path):
    """
    When there is no legacy directory `migrate_containers` does not
    create a new directory and returns False.
    """
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    assert cli.migrate_containers(src, dst) is False
    assert not src.exists()
    assert not dst.exists()


def test_telegraf_migrate_empty(tmp_path):
    """
    When the legacy directory exists, `migrate_containers` moves the
    directory and returns True.
    """
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    src.mkdir()
    assert cli.migrate_containers(src, dst) is True
    assert not src.exists()
    assert dst.exists()
    assert not any(dst.iterdir())


def test_telegraf_migrate_not_empty(tmp_path):
    """
    Migration moves legacy files.
    """
    file_contents = b'1234'
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    src.mkdir()
    file = src / 'file'
    file.write_bytes(file_contents)
    assert cli.migrate_containers(src, dst) is True
    assert not src.exists()
    assert dst.exists()
    file = dst / 'file'
    assert list(dst.iterdir()) == [file]
    assert file.read_bytes() == file_contents


def test_telegraf_migrate_dst_exists_empty(tmp_path):
    """
    Migration works if the target directory exists but is empty.
    """
    file_contents = b'1234'
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    src.mkdir()
    file = src / 'file'
    file.write_bytes(file_contents)
    dst.mkdir()
    assert cli.migrate_containers(src, dst) is True
    assert not src.exists()
    assert dst.exists()
    file = dst / 'file'
    assert list(dst.iterdir()) == [file]
    assert file.read_bytes() == file_contents


def test_telegraf_migrate_dst_exists_not_empty(tmp_path):
    """
    Migration fails if the target directory contains files.
    """
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
