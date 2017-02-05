import shutil

import pytest
from docopt import DocoptExit

from launch.cli import main


def test_no_files_specified(tmpdir, aws_cf_config_path):
    """Ensure typical usage works without specifying config and info file paths
    """
    with tmpdir.as_cwd():
        shutil.copyfile(aws_cf_config_path, str(tmpdir.join('config.yaml')))
        assert main(['create']) == 0
        assert main(['wait']) == 0
        assert main(['describe']) == 0
        assert main(['pytest']) == 0
        assert main(['delete']) == 0


def test_noop():
    """Ensure docopt exit (displays usage)
    """
    with pytest.raises(DocoptExit):
        main([])
    with pytest.raises(DocoptExit):
        main(['foobar'])


def test_conflicting_path(tmpdir, aws_cf_config_path):
    """Ensure default cluster info path is never overwritten
    by launching successive clusters
    """
    with tmpdir.as_cwd():
        shutil.copyfile(aws_cf_config_path, str(tmpdir.join('config.yaml')))
        assert main(['create']) == 0
        assert main(['create']) == 1


def test_missing_input(tmpdir):
    """No files are provided so any operation should fail
    """
    with tmpdir.as_cwd():
        for cmd in ['create', 'wait', 'describe', 'delete', 'pytest']:
            with pytest.raises(FileNotFoundError):
                main([cmd])
