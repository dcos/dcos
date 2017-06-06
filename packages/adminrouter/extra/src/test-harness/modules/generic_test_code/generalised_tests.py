# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import copy
import logging
import os

import yaml

from generic_test_code.common import (
    assert_endpoint_response,
    generic_correct_upstream_dest_test,
    generic_correct_upstream_request_test,
    generic_location_header_during_redirect_is_adjusted_test,
    generic_no_slash_redirect_test,
    generic_response_headers_verify_test,
    generic_upstream_headers_verify_test,
)

log = logging.getLogger(__name__)

# Generalised tests were moved to a separate library included by
# test-harness/tests/(open|ee)/test_generic.py files because they
# may require fixturesd from test-harness/tests/(open|ee)/conftest.py which
# in turn is not reachable/included by test-harness/tests/test_generic.py
# file.


def _merge_testconfig(a, b):
    res = {'endpoint_tests': [],
           }

    res['endpoint_tests'].extend(
        copy.deepcopy(a['endpoint_tests']))

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


def _verify_type_specification(types):
    assert len(set(types)) in [1, 2]
    for k in types:
        assert k in ['master', 'agent']


def _verify_endpoint_tests_conf(endpoint_tests):
    for t in endpoint_tests:
        _check_all_keys_are_present_in_dict(t, ['tests', 'type'])
        _verify_type_specification(t['type'])

        at_least_one_test_enabled = False
        assert 0 < len(t['tests'].keys()) < 7
        for k in t['tests']:
            assert 'enabled' in t['tests'][k]
            assert t['tests'][k]['enabled'] in [True, False]
            at_least_one_test_enabled = at_least_one_test_enabled or \
                t['tests'][k]['enabled']

        assert at_least_one_test_enabled

        if 'is_endpoint_redirecting_properly' in t['tests']:
            _verify_is_endpoint_redirecting_properly(
                t['tests']['is_endpoint_redirecting_properly'])
        if 'is_location_header_rewritten' in t['tests']:
            _verify_is_location_header_rewritten(
                t['tests']['is_location_header_rewritten'])
        if 'is_upstream_correct' in t['tests']:
            _verify_is_upstream_correct_test_conf(
                t['tests']['is_upstream_correct'])
        if 'is_upstream_req_ok' in t['tests']:
            _verify_is_upstream_req_ok_test_conf(
                t['tests']['is_upstream_req_ok'])
        if 'are_upstream_req_headers_ok' in t['tests']:
            _verify_are_upstream_req_headers_ok(
                t['tests']['are_upstream_req_headers_ok'])
        if 'are_response_headers_ok' in t['tests']:
            _verify_are_response_headers_ok(
                t['tests']['are_response_headers_ok'])
        if 'is_unauthed_access_permitted' in t['tests']:
            _verify_is_unauthed_access_permitted(
                t['tests']['is_unauthed_access_permitted'])


def _verify_is_location_header_rewritten(t_config):
    if not t_config['enabled']:
        return

    _check_all_keys_are_present_in_dict(
        t_config,
        ['basepath', 'endpoint_id', 'redirect_testscases', 'enabled'])

    assert t_config['endpoint_id'].startswith('http')
    assert t_config['basepath'].startswith('/')

    rt_testc = t_config['redirect_testscases']
    assert len(rt_testc) > 0
    for rt in rt_testc:
        keys = ['location_expected', 'location_expected']
        _check_all_keys_are_present_in_dict(rt, keys)
        for k in keys:
            assert k in rt
            assert len(rt[k]) > 0


def _verify_is_endpoint_redirecting_properly(t_config):
    if not t_config['enabled']:
        return

    assert 'locations' in t_config

    assert len(t_config['locations']) > 0
    for p in t_config['locations']:
        assert p.startswith('/')


def _verify_is_unauthed_access_permitted(t_config):
    if not t_config['enabled']:
        return

    assert 'locations' in t_config

    assert len(t_config['locations']) > 0
    for p in t_config['locations']:
        assert p.startswith('/')


def _verify_is_upstream_correct_test_conf(t_config):
    if not t_config['enabled']:
        return

    assert 'upstream' in t_config
    assert t_config['upstream'].startswith('http')

    assert 'test_paths' in t_config
    for p in t_config['test_paths']:
        assert p.startswith('/')


def _verify_is_upstream_req_ok_test_conf(t_config):
    if not t_config['enabled']:
        return

    assert 'expected_http_ver' in t_config
    assert t_config['expected_http_ver'] in ['HTTP/1.0', 'HTTP/1.1', 'websockets']

    assert 'test_paths' in t_config
    for p in t_config['test_paths']:
        _check_all_keys_are_present_in_dict(p, ['expected', 'sent'])


def _verify_are_upstream_req_headers_ok(t_config):
    if not t_config['enabled']:
        return

    assert 'jwt_should_be_forwarded' in t_config
    assert t_config['jwt_should_be_forwarded'] in [True, False, 'skip']

    assert 'test_paths' in t_config
    for p in t_config['test_paths']:
        assert p.startswith('/')


def _verify_are_response_headers_ok(t_config):
    if not t_config['enabled']:
        return

    assert 'nocaching_headers_are_sent' in t_config
    assert t_config['nocaching_headers_are_sent'] in [True, False, 'skip']

    assert 'test_paths' in t_config
    for p in t_config['test_paths']:
        assert p.startswith('/')


def _tests_configuration(path):
    common_tests_conf_file = os.path.join(path, "..", "test_generic.config.yml")
    with open(common_tests_conf_file, 'r') as fh:
        common_tests_conf = yaml.load(fh)

    flavoured_tests_conf_file = os.path.join(path, "test_generic.config.yml")
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

    for x in tests_config['endpoint_tests']:
        if node_type not in x['type']:
            continue

        if 'is_location_header_rewritten' not in x['tests']:
            continue

        h = x['tests']['is_location_header_rewritten']
        if h['enabled'] is not True:
            continue

        for l in h['redirect_testscases']:
            res.append(
                (h['endpoint_id'],
                 h['basepath'],
                 l['location_set'],
                 l['location_expected']),
            )

    return res


def _testdata_to_is_unauthed_access_permitted(tests_config, node_type):
    res = []

    for x in tests_config['endpoint_tests']:
        if node_type not in x['type']:
            continue

        if 'is_unauthed_access_permitted' not in x['tests']:
            continue

        h = x['tests']['is_unauthed_access_permitted']
        if h['enabled'] is not True:
            continue

        res.extend(h['locations'])

    return res


def _testdata_to_are_response_headers_ok(tests_config, node_type):
    res = []

    for x in tests_config['endpoint_tests']:
        if node_type not in x['type']:
            continue

        if 'are_response_headers_ok' not in x['tests']:
            continue

        h = x['tests']['are_response_headers_ok']
        if h['enabled'] is not True:
            continue

        res.extend([(x, h['nocaching_headers_are_sent']) for x in h['test_paths']])

    return res


def _testdata_to_redirect_testdata(tests_config, node_type):
    res = []

    for x in tests_config['endpoint_tests']:
        if node_type not in x['type']:
            continue

        if 'is_endpoint_redirecting_properly' not in x['tests']:
            continue

        h = x['tests']['is_endpoint_redirecting_properly']
        if h['enabled'] is not True:
            continue

        res.extend(h['locations'])

    return res


def create_tests(metafunc, path):
    tests_config = _tests_configuration(path)
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

    if 'unauthed_path' in metafunc.fixturenames:
        args = _testdata_to_is_unauthed_access_permitted(tests_config, ar_type)
        metafunc.parametrize("unauthed_path", args)
        return

    if 'caching_headers_test' in metafunc.fixturenames:
        args = _testdata_to_are_response_headers_ok(tests_config, ar_type)
        metafunc.parametrize("path,caching_headers_test", args)
        return


class GenericTestMasterClass:
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

        headers_present = {}
        headers_absent = []

        if jwt_forwarded_test is True:
            headers_present.update(valid_user_header)
        elif jwt_forwarded_test is False:
            headers_absent.append("Authorization")
        # jwt_forwarded_test == "skip", do nothing

        generic_upstream_headers_verify_test(
            master_ar_process_perclass,
            valid_user_header,
            path,
            assert_headers=headers_present,
            assert_headers_absent=headers_absent,
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

    def test_if_unauthn_user_is_granted_access(
            self, master_ar_process_perclass, unauthed_path):
        assert_endpoint_response(master_ar_process_perclass, unauthed_path, 200)

    def test_if_resp_headers_are_correct(
            self,
            master_ar_process_perclass,
            valid_user_header,
            path,
            caching_headers_test,
            ):

        headers_present = {}
        headers_absent = []

        if caching_headers_test is True:
            headers_present['Cache-Control'] = "no-cache, no-store, must-revalidate"
            headers_present['Pragma'] = "no-cache"
            headers_present['Expires'] = "0"
        elif caching_headers_test is False:
            headers_absent.append("Cache-Control")
            headers_absent.append("Pragma")
            headers_absent.append("Expires")
        # caching_headers_test == "skip", do nothing

        generic_response_headers_verify_test(
            master_ar_process_perclass,
            valid_user_header,
            path,
            assert_headers=headers_present,
            assert_headers_absent=headers_absent,
            )


class GenericTestAgentClass:
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

        headers_present = {}
        headers_absent = []

        if jwt_forwarded_test is True:
            headers_present.update(valid_user_header)
        elif jwt_forwarded_test is False:
            headers_absent.append("Authorization")
        # jwt_forwarded_test == "skip", do nothing

        generic_upstream_headers_verify_test(
            agent_ar_process_perclass,
            valid_user_header,
            path,
            assert_headers=headers_present,
            assert_headers_absent=headers_absent,
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

    def test_if_unauthn_user_is_granted_access(
            self, agent_ar_process_perclass, unauthed_path):
        assert_endpoint_response(agent_ar_process_perclass, unauthed_path, 200)

    def test_if_resp_headers_are_correct(
            self,
            agent_ar_process_perclass,
            valid_user_header,
            path,
            caching_headers_test,
            ):

        headers_present = {}
        headers_absent = []

        if caching_headers_test is True:
            headers_present['Cache-Control'] = "no-cache, no-store, must-revalidate"
            headers_present['Pragma'] = "no-cache"
            headers_present['Expires'] = "0"
        elif caching_headers_test is False:
            headers_absent.append("Cache-Control")
            headers_absent.append("Pragma")
            headers_absent.append("Expires")
        # caching_headers_test == "skip", do nothing

        generic_response_headers_verify_test(
            agent_ar_process_perclass,
            valid_user_header,
            path,
            assert_headers=headers_present,
            assert_headers_absent=headers_absent,
            )
