import glob
import logging
import os
import pathlib
import stat
import subprocess

import pytest


@pytest.mark.supportedwindows
def test_verify_units():
    """Test that all systemd units are valid."""
    def _check_units(path):
        """Verify all the units given by `path'"""
        for file in glob.glob(path):
            cmd = subprocess.run(
                ["/usr/bin/systemd-analyze", "verify", "--no-pager", file],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True)
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

                for line in cmd.stdout.split("\n"):
                    if not _check_line(line):
                        pytest.fail("Invalid systemd unit: " + line)

    _check_units("/etc/systemd/system/dcos-*.service")
    _check_units("/etc/systemd/system/dcos-*.socket")


@pytest.mark.supportedwindows
def test_socket_units():
    """Test that socket units configure socket files in /run/dcos
    that are owned by 'dcos_adminrouter'.
    """
    def _check_unit(file):
        logging.info("Checking socket unit {}".format(file))
        out = subprocess.check_output(
            ["/usr/bin/systemctl", "show", "--no-pager", os.path.basename(file)],
            stderr=subprocess.STDOUT,
            universal_newlines=True)
        user = ""
        group = ""
        mode = ""
        had_unix_socket = False
        for line in out.split("\n"):
            parts = line.split("=")
            if len(parts) != 2:
                continue
            k, v = parts
            if k == "SocketUser":
                user = v
            if k == "SocketGroup":
                group = v
            if k == "ListenStream":
                # Unix sockets are distinguished from IP sockets by having a '/' as the first
                # character in the value of the ListenStream directive.
                if v.startswith("/"):
                    had_unix_socket = True
                    assert v.startswith("/run/dcos/"), "DC/OS unix sockets must go in the /run/dcos directory"
            if k == "SocketMode":
                mode = v
        if not had_unix_socket:
            # This socket file doesn't declare any unix sockets, ignore.
            return
        assert user == "root"
        assert group == "dcos_adminrouter"
        assert mode == "0660"

    for file in glob.glob("/etc/systemd/system/dcos-*.socket"):
        _check_unit(file)


@pytest.mark.supportedwindows
def test_socket_files():
    """Test that all socket files in /run/dcos are owned by 'dcos_adminrouter'."""
    for file in glob.glob("/run/dcos/*"):
        path = pathlib.Path(file)
        if not path.is_socket():
            # This is not a unix socket file, ignore.
            continue
        logging.info("Checking socket file {}".format(file))
        assert path.owner() == "root"
        assert path.group() == "dcos_adminrouter"
        assert stat.S_IMODE(path.stat().st_mode) == 0o660
