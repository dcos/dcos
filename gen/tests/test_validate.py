import logging

import gen
from gen.build_deploy.bash import onprem_source


# TODO(cmaloney): Should be able to pass an exact tree to gen so that we can test
# one little piece at a time rather than having to rework this every time that
# DC/OS parameters change.
def test_error_during_calc(monkeypatch):
    monkeypatch.setenv('BOOTSTRAP_ID', 'foobar')
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    assert gen.validate({
        'ip_detect_filename': 'not-a-existing-file',
        'bootstrap_variant': '',
    }, extra_sources=[onprem_source]) == {
        'status': 'errors',
        'errors': {
            'ip_detect_contents': {'message': 'ip-detect script `not-a-existing-file` must exist'}
        },
        'unset': {
            'bootstrap_url',
            'cluster_name',
            'exhibitor_storage_backend',
            'master_discovery'
        }
    }


def test_error_during_validate(monkeypatch):
    monkeypatch.setenv('BOOTSTRAP_ID', 'foobar')
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    assert gen.validate({
        'bootstrap_url': '',
        'bootstrap_variant': '',
        'ip_detect_contents': '',  # so that ip_detect_filename doesn't get used from onprem_source
        'ip6_detect_contents': '',
        'exhibitor_storage_backend': 'static',
        'master_discovery': 'static',
        'cluster_name': 'foobar',
        'master_list': '["127.0.0.1"]',
    }, extra_sources=[onprem_source]) == {
        'status': 'errors',
        'errors': {
            'bootstrap_url': {'message': 'Should be a url (http://example.com/bar or file:///path/to/local/cache)'},
        },
        'unset': set()
    }


def test_error_during_validate_calico_network(monkeypatch):
    monkeypatch.setenv('BOOTSTRAP_ID', 'foobar')
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    assert gen.validate({
        'bootstrap_url': '',
        'bootstrap_variant': '',
        'ip_detect_contents': '',  # so that ip_detect_filename doesn't get used from onprem_source
        'ip6_detect_contents': '',
        'exhibitor_storage_backend': 'static',
        'master_discovery': 'static',
        'cluster_name': 'foobar',
        'master_list': '["127.0.0.1"]',
        'calico_network_cidr': '',
    }, extra_sources=[onprem_source]) == {
        'status': 'errors',
        'errors': {
            'calico_network_cidr': {
                'message': 'Incorrect value for `calico_network_cidr`: ``. Only IPv4 subnets are allowed'
            },
            'bootstrap_url': {
                'message': 'Should be a url (http://example.com/bar or file:///path/to/local/cache)'
            }
        },
        'unset': set()
    }
