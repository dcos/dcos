# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""This module sets up pytest hooks

    Please check pytest documentation and/or util module docstrings.
"""

import pytest

import util


def pytest_addoption(parser):
    parser.addoption('--log-level', '-L',
                     type='choice',
                     action='store',
                     dest='tests_log_level',
                     choices=['disabled', 'debug', 'info', 'warning',
                              'error', 'critical'],
                     default='disabled',
                     help='Set verbosity of the testing framework.',)


def pytest_configure(config):
    util.setup_thread_debugger()
    util.configure_logger(config)


pytest.register_assert_rewrite('generic_test_code.common')
pytest.register_assert_rewrite('generic_test_code.open')
