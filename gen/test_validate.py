import json
import logging

import gen


# TODO(cmaloney): Should be able to pass an exact tree to gen so that we can test
# one little piece at a time rather than having to rework this every time that
# DC/OS parameters change.
def test_error_during_calc():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    assert gen.validate({
            'ip_detect_filename': 'not-a-existing-file',
            'provider': 'onprem',
            'bootstrap_variant': '',
            'package_ids': json.dumps([])
        }) == {
            'status': 'errors',
            'errors': {
                'ip_detect_contents': {'message': 'ip-detect script: not-a-existing-file must exist'}
            },
            'unset': {
                'bootstrap_id',
                'bootstrap_url',
                'cluster_name',
                'exhibitor_storage_backend',
                'master_discovery'
            }
        }


def test_error_during_validate():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    assert gen.validate({
            'bootstrap_url': '',
            'bootstrap_variant': '',
            'package_ids': json.dumps([])
        }) == {
            'status': 'errors',
            'errors': {
                'bootstrap_url': {'message': 'Should be a url (http://example.com/bar or file:///path/to/local/cache)'}
            },
            'unset': {
                'bootstrap_id',
                'provider',
            }
        }
