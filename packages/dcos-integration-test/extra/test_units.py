import glob
import subprocess

import pytest


def test_verify_units():
    """Test that all systemd units are valid."""
    def _check_units(path):
        """Verify all the units given by `path'"""
        for file in glob.glob(path):
            cmd = subprocess.run(
                ["/usr/bin/systemd-analyze", "verify", "--no-pager", file],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT)
            # systemd-analyze returns 0 even if there were warnings, so we
            # assert that the command output was empty.
            if cmd.stdout:
                # We specifically allow directives that exist in newer systemd
                # versions but will cause older systemd versions to complain.
                # The "old" systemd version we are using as a baseline is
                # systemd 219, which ships with CentOS 7.2.1511.
                def _check_line(line):
                    # `systemd-analyze verify` checks for errors in the given
                    # unit files, as well as other files that are loaded
                    # transitively. We do not want our tests to fail when
                    # third-party software ships bad unit files, so we
                    # explicitly check that 'dcos-' is present on a
                    # line before checking if it is valid.
                    if "dcos-" not in line:
                        return True
                    # The TasksMax directive exists in newer versions of systemd
                    # where it is important to set. As we want to support multiple
                    # versions of systemd our tests must ignore errors that
                    # complain that it is an unknown directive.
                    ignore_new_directives = ["TasksMax"]
                    for directive in ignore_new_directives:
                        if directive not in line:
                            # since this line contains 'dcos-' and the error is
                            # not for one of the directives that we specifically
                            # ignore in order to be future-proof we return False
                            # to signal that in truth this line complains of
                            # a systemd configuration error.
                            return False
                    return True

                for line in cmd.stdout.decode("utf-8").split("\n"):
                    if not _check_line(line):
                        pytest.fail("Invalid systemd unit: " + line)

    _check_units("/etc/systemd/system/dcos-*.service")
    _check_units("/etc/systemd/system/dcos-*.socket")
