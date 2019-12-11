from common.utils import transfer_files

EXPECTED_FILE_CONTENT = 'test'


def check_file(path):
    assert path.exists()
    with path.open() as f:
        contents = f.read()
    assert contents == EXPECTED_FILE_CONTENT


def test_transfer_files(tmp_path):
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    src.mkdir()
    dst.mkdir()
    (src / 'sub').mkdir()
    with (src / 'file1').open('w') as f:
        f.write(EXPECTED_FILE_CONTENT)
    with (src / 'sub' / 'file2').open('w') as f:
        f.write(EXPECTED_FILE_CONTENT)
    transfer_files(str(src), str(dst))
    check_file(dst / 'file1')
    check_file(dst / 'sub' / 'file2')
