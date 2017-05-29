# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import os

from generic_test_code.generalised_tests import (
    create_tests,
    GenericTestMasterClass,
    GenericTestAgentClass,
)

# Please check comment at the top of
# test-harness/modules/generic_test_code/generalised_tests.py
# for explanation why this test code is structured this way.


def pytest_generate_tests(metafunc):
    create_tests(metafunc, os.path.dirname(os.path.abspath(__file__)))


class TestMasterGeneric(GenericTestMasterClass):
    pass


class TestAgentGeneric(GenericTestAgentClass):
    pass
