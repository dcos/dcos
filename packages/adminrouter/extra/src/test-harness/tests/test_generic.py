# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import copy
import logging
import os

import yaml

import generic_test_code.common
from generic_test_code.common import (
    generic_correct_upstream_dest_test,
    generic_correct_upstream_request_test,
    generic_location_header_during_redirect_is_adjusted_test,
    generic_no_slash_redirect_test,
    generic_upstream_headers_verify_test,
)

log = logging.getLogger(__name__)


def _merge_testconfig(a, b):
    res = {'redirect_tests': [],
           'location_header_rewrite_tests': [],
           'endpoint_tests': [],
           }

    res['redirect_tests'].extend(
        copy.deepcopy(a['redirect_tests']))
    res['location_header_rewrite_tests'].extend(
        copy.deepcopy(a['location_header_rewrite_tests']))
    res['endpoint_tests'].extend(
        copy.deepcopy(a['endpoint_tests']))

    res['redirect_tests'].extend(
        copy.deepcopy(b['redirect_tests']))
    res['location_header_rewrite_tests'].extend(
        copy.deepcopy(b['location_header_rewrite_tests']))
    res['endpoint_tests'].extend(
        copy.deepcopy(b['endpoint_tests']))

    return res


def _check_all_keys_are_present_in_dict(d, keys):
    assert len(d.keys()) == len(keys)
    for k in keys:
        assert k in d


def _verify_tests_conf(tests_conf):
    # TODO (prozlach): rewrite all of these to Json Schema validation, quick
    # hack for now
    _verify_endpoint_tests_conf(tests_conf['endpoint_tests'])
    _verify_location_rewrite_tests(tests_conf['location_header_rewrite_tests'])
    _verify_redirect_tests(tests_conf['redirect_tests'])


def _verify_type_specification(types):
    assert len(set(types)) in [1, 2]
    for k in types:
        assert k in ['master', 'agent']


def _verify_redirect_tests(redirect_tests):
    for t in redirect_tests:
        _check_all_keys_are_present_in_dict(t, ['endpoints', 'type'])
        _verify_type_specification(t['type'])

        assert len(t['endpoints']) > 0

        for e in t['endpoints']:
            assert e.startswith('/')


def _verify_location_rewrite_tests(location_rewrite_tests):
    for t in location_rewrite_tests:
        _check_all_keys_are_present_in_dict(
            t, ['basepath', 'endpoint_id', 'redirect_testscases', 'type'])
        _verify_type_specification(t['type'])

        assert t['endpoint_id'].startswith('http')
        assert t['basepath'].startswith('/')

        rt_testc = t['redirect_testscases']
        assert len(rt_testc) > 0
        for rt in rt_testc:
            assert len(rt.keys()) == 2
            for k in ['location_expected', 'location_expected']:
                assert k in rt
                assert len(rt[k]) > 0


def _verify_endpoint_tests_conf(endpoint_tests):
    for t in endpoint_tests:
        _check_all_keys_are_present_in_dict(t, ['tests', 'type'])
        _verify_type_specification(t['type'])

        at_least_one_test_enabled = False
        assert len(t['tests'].keys()) in [1, 2, 3]
        for k in ['is_upstream_correct',
                  'are_upstream_req_headers_ok',
                  'is_upstream_req_ok']:
            if k in t['tests']:
                assert 'enabled' in t['tests'][k]
                assert t['tests'][k]['enabled'] in [True, False]
                at_least_one_test_enabled = at_least_one_test_enabled or \
                    t['tests'][k]['enabled']

        assert at_least_one_test_enabled

        if 'is_upstream_correct' in t['tests']:
            _verify_is_upstream_correct_test_conf(
                t['tests']['is_upstream_correct'])
        if 'is_upstream_req_ok' in t['tests']:
            _verify_is_upstream_req_ok_test_conf(
                t['tests']['is_upstream_req_ok'])
        if 'are_upstream_req_headers_ok' in t['tests']:
            _verify_jwt_should_be_forwarded_test_conf(
                t['tests']['are_upstream_req_headers_ok'])


def _verify_is_upstream_correct_test_conf(t_config):
    if t_config['enabled']:
        assert 'upstream' in t_config
        assert t_config['upstream'].startswith('http')

        assert 'test_paths' in t_config
        for p in t_config['test_paths']:
            assert p.startswith('/')


def _verify_is_upstream_req_ok_test_conf(t_config):
    if t_config['enabled']:
        assert 'expected_http_ver' in t_config
        assert t_config['expected_http_ver'] in ['HTTP/1.0', 'HTTP/1.1']

        assert 'test_paths' in t_config
        for p in t_config['test_paths']:
            _check_all_keys_are_present_in_dict(p, ['expected', 'sent'])


def _verify_jwt_should_be_forwarded_test_conf(t_config):
    if t_config['enabled']:
        assert 'jwt_should_be_forwarded' in t_config
        assert t_config['jwt_should_be_forwarded'] in [True, False, 'skip']

        assert 'test_paths' in t_config
        for p in t_config['test_paths']:
            assert p.startswith('/')


def _tests_configuration():
    curdir = os.path.dirname(os.path.abspath(__file__))
    common_tests_conf_file = os.path.join(curdir, "test_generic.config.yml")
    with open(common_tests_conf_file, 'r') as fh:
        common_tests_conf = yaml.load(fh)

    if generic_test_code.common.repo_is_ee():
        flavour_dir = 'ee'
    else:
        flavour_dir = 'open'

    flavoured_tests_conf_file = os.path.join(
        curdir, flavour_dir, "test_generic.config.yml")
    with open(flavoured_tests_conf_file, 'r') as fh:
        flavoured_tests_conf = yaml.load(fh)

    tests_conf = _merge_testconfig(common_tests_conf, flavoured_tests_conf)
    _verify_tests_conf(tests_conf)

    return tests_conf


def _testdata_to_is_upstream_correct_testdata(tests_config, node_type):
    res = []

    for x in tests_config['endpoint_tests']:
        if node_type not in x['type']:
            continue

        if 'is_upstream_correct' not in x['tests']:
            continue

        h = x['tests']['is_upstream_correct']
        if h['enabled'] is not True:
            continue

        for p in h['test_paths']:
            e = (p, h['upstream'])
            res.append(e)

    return res


def _testdata_to_is_upstream_req_ok_testdata(tests_config, node_type):
    res = []

    for x in tests_config['endpoint_tests']:
        if node_type not in x['type']:
            continue

        if 'is_upstream_req_ok' not in x['tests']:
            continue

        h = x['tests']['is_upstream_req_ok']
        if h['enabled'] is not True:
            continue

        for p in h['test_paths']:
            e = (p['sent'], p['expected'], h['expected_http_ver'])
            res.append(e)

    return res


def _testdata_to_are_upstream_req_headers_ok_testdata(tests_config, node_type):
    res = []

    for x in tests_config['endpoint_tests']:
        if node_type not in x['type']:
            continue

        if 'are_upstream_req_headers_ok' not in x['tests']:
            continue

        h = x['tests']['are_upstream_req_headers_ok']
        if h['enabled'] is not True:
            continue

        for p in h['test_paths']:
            e = (p, h['jwt_should_be_forwarded'])
            res.append(e)

    return res


def _testdata_to_location_header_rewrite_testdata(tests_config, node_type):
    res = []

    for x in tests_config['location_header_rewrite_tests']:
        if node_type not in x['type']:
            continue

        for l in x['redirect_testscases']:
            res.append(
                (x['endpoint_id'],
                 x['basepath'],
                 l['location_set'],
                 l['location_expected']),
            )

    return res


def _testdata_to_redirect_testdata(tests_config, node_type):
    res = []

    for x in tests_config['redirect_tests']:
        if node_type not in x['type']:
            continue

        res.extend(x['endpoints'])

    return res


def pytest_generate_tests(metafunc):
    tests_config = _tests_configuration()
    if 'master_ar_process_perclass' in metafunc.fixturenames:
        ar_type = 'master'
    else:
        ar_type = 'agent'

    if set(['path', 'expected_upstream']) <= set(metafunc.fixturenames):
        args = _testdata_to_is_upstream_correct_testdata(tests_config, ar_type)
        metafunc.parametrize("path,expected_upstream", args)
        return

    if set(['path', 'jwt_forwarded_test']) <= set(metafunc.fixturenames):
        args = _testdata_to_are_upstream_req_headers_ok_testdata(tests_config, ar_type)
        metafunc.parametrize("path,jwt_forwarded_test", args)
        return

    if set(['path', 'upstream_path', 'http_ver']) <= set(metafunc.fixturenames):
        args = _testdata_to_is_upstream_req_ok_testdata(tests_config, ar_type)
        metafunc.parametrize("path,upstream_path,http_ver", args)
        return

    f_names = ['endpoint_id', 'basepath', 'location_set', 'location_expected']
    if set(f_names) <= set(metafunc.fixturenames):
        args = _testdata_to_location_header_rewrite_testdata(tests_config, ar_type)
        metafunc.parametrize(','.join(f_names), args)
        return

    if 'redirect_path' in metafunc.fixturenames:
        args = _testdata_to_redirect_testdata(tests_config, ar_type)
        metafunc.parametrize("redirect_path", args)
        return


class TestMasterGeneric:
    def test_if_request_is_sent_to_correct_upstream(
            self,
            master_ar_process_perclass,
            valid_user_header,
            path,
            expected_upstream):

        generic_correct_upstream_dest_test(
            master_ar_process_perclass,
            valid_user_header,
            path,
            expected_upstream,
            )

    def test_if_upstream_headers_are_correct(
            self,
            master_ar_process_perclass,
            valid_user_header,
            path,
            jwt_forwarded_test,
            ):

        if jwt_forwarded_test is True:
            generic_upstream_headers_verify_test(
                master_ar_process_perclass,
                valid_user_header,
                path,
                assert_headers=valid_user_header,
            )
        elif jwt_forwarded_test is False:
            generic_upstream_headers_verify_test(
                master_ar_process_perclass,
                valid_user_header,
                path,
                assert_headers_absent=["Authorization"]
                )

        # None == 'skip'
        else:
            generic_upstream_headers_verify_test(
                master_ar_process_perclass,
                valid_user_header,
                path,
                )

    def test_if_upstream_request_is_correct(
            self,
            master_ar_process_perclass,
            valid_user_header,
            path,
            upstream_path,
            http_ver):

        generic_correct_upstream_request_test(
            master_ar_process_perclass,
            valid_user_header,
            path,
            upstream_path,
            http_ver,
            )

    def test_if_location_header_during_redirect_is_adjusted(
            self,
            master_ar_process_perclass,
            mocker,
            valid_user_header,
            endpoint_id,
            basepath,
            location_set,
            location_expected,
            ):

        generic_location_header_during_redirect_is_adjusted_test(
            master_ar_process_perclass,
            mocker,
            valid_user_header,
            endpoint_id,
            basepath,
            location_set,
            location_expected,
            )

    def test_redirect_req_without_slash(
            self, master_ar_process_perclass, redirect_path):
        generic_no_slash_redirect_test(master_ar_process_perclass, redirect_path)


class TestAgentGeneric:
    def test_if_request_is_sent_to_correct_upstream(
            self,
            agent_ar_process_perclass,
            valid_user_header,
            path,
            expected_upstream):

        generic_correct_upstream_dest_test(
            agent_ar_process_perclass,
            valid_user_header,
            path,
            expected_upstream,
            )

    def test_if_upstream_headers_are_correct(
            self,
            agent_ar_process_perclass,
            valid_user_header,
            path,
            jwt_forwarded_test,
            ):

        if jwt_forwarded_test is True:
            generic_upstream_headers_verify_test(
                agent_ar_process_perclass,
                valid_user_header,
                path,
                assert_headers=valid_user_header,
            )
        elif jwt_forwarded_test is False:
            generic_upstream_headers_verify_test(
                agent_ar_process_perclass,
                valid_user_header,
                path,
                assert_headers_absent=["Authorization"]
                )

        # None == 'skip'
        else:
            generic_upstream_headers_verify_test(
                agent_ar_process_perclass,
                valid_user_header,
                path,
                )

    def test_if_upstream_request_is_correct(
            self,
            agent_ar_process_perclass,
            valid_user_header,
            path,
            upstream_path,
            http_ver):

        generic_correct_upstream_request_test(
            agent_ar_process_perclass,
            valid_user_header,
            path,
            upstream_path,
            http_ver,
            )

    def test_if_location_header_during_redirect_is_adjusted(
            self,
            agent_ar_process_perclass,
            mocker,
            valid_user_header,
            endpoint_id,
            basepath,
            location_set,
            location_expected,
            ):

        generic_location_header_during_redirect_is_adjusted_test(
            agent_ar_process_perclass,
            mocker,
            valid_user_header,
            endpoint_id,
            basepath,
            location_set,
            location_expected,
            )

    def test_redirect_req_without_slash(
            self, agent_ar_process_perclass, redirect_path):
        generic_no_slash_redirect_test(agent_ar_process_perclass, redirect_path)
