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
                        # When systemd does not understand a directive it
                        # prints a line with the following format:
                        #
                        #    [/etc/systemd/system/foo.service:5] Unknown lvalue 'EExecStat' in section 'Service'
                        #
                        # We ignore such errors when the lvalue is one of the
                        # well-known directives that got added to newer
                        # versions of systemd.
                        unknown_lvalue_err = "Unknown lvalue '%s'" % directive
                        if unknown_lvalue_err in line:
                            # This version of systemd does not understand this
                            # directive. It got added in newer versions.
                            # As systemd ignores directives it does not
                            # understand this is not a problem and we simply
                            # ignore this error.
                            pass
                        else:
                            # Whatever problem systemd-analyze sees in this
                            # line is more significant than a simple
                            # 'unknown lvalue' complaint. We treat it as a
                            # valid issue and fail.
                            return False
                    return True

                for line in cmd.stdout.decode("utf-8").split("\n"):
                    if not _check_line(line):
                        pytest.fail("Invalid systemd unit: " + line)

    _check_units("/etc/systemd/system/dcos-*.service")
    _check_units("/etc/systemd/system/dcos-*.socket")
