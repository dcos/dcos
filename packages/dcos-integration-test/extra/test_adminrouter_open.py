import logging
import re
import uuid

import pytest

from dcos_test_utils.dcos_api import DcosApiSession
from retrying import retry


log = logging.getLogger(__name__)


@pytest.mark.security
class TestRedirectSecurity:

    @pytest.mark.parametrize(
        'path,expected', (
            ('/exhibitor', 301),
            ('/exhibitor/', 302),
            ('/marathon', 307),
            ('/mesos', 301),
            ('/mesos/master/redirect', 307),
            ('/mesos_dns', 301),
            ('/net', 301),
            ('/pkgpanda/repository', 301),
            ('/service/marathon', 301),
            ('/service/test-service', 301),
            ('/system/v1/logs', 301),
            ('/system/v1/metrics', 301),
        )
    )
    def test_redirect_host(self, dcos_api_session: DcosApiSession, path: str, expected: str) -> None:
        """
        Redirection does not propagate a bad Host header
        """
        r = dcos_api_session.get(
            path,
            headers={'Host': 'bad.host'},
            allow_redirects=False
        )

        r.raise_for_status()

        assert r.status_code == expected
        assert 'bad.host' not in r.headers['Location']


class TestEncodingGzip:

    # This pattern should provide `index.css` and `index.js` files.
    pat = re.compile(r'/assets/index\.[^"]+')

    def test_accept_gzip(self, dcos_api_session: DcosApiSession) -> None:
        """
        Clients that send "Accept-Encoding: gzip" get gzipped responses
        for some assets.
        """
        r = dcos_api_session.get('/')
        r.raise_for_status()
        filenames = self.pat.findall(r.text)
        assert len(filenames) > 0
        for filename in set(filenames):
            log.info('Load %r', filename)
            r = dcos_api_session.head(filename, headers={'Accept-Encoding': 'gzip'})
            r.raise_for_status()
            log.info('Response headers: %s', repr(r.headers))
            assert r.headers.get('content-encoding') == 'gzip'

    def test_not_accept_gzip(self, dcos_api_session: DcosApiSession) -> None:
        """
        Clients that do not send "Accept-Encoding: gzip" do not get gzipped
        responses.
        """
        r = dcos_api_session.get('/')
        r.raise_for_status()
        filenames = self.pat.findall(r.text)
        assert len(filenames) > 0
        for filename in set(filenames):
            log.info('Load %r', filename)
            # Set a benign `Accept-Encoding` header to prevent underlying
            # libraries setting their own header based on their capabilities.
            r = dcos_api_session.head(filename, headers={'Accept-Encoding': 'identity'})
            r.raise_for_status()
            log.info('Response headers: %s', repr(r.headers))
            assert 'content-encoding' not in r.headers


class TestStateCacheUpdate:
    """
    Tests for Admin Router correctly updating its Mesos/Marathon state cache.
    """

    def test_invalid_dcos_service_port_index(self, dcos_api_session: DcosApiSession) -> None:
        """
        An invalid `DCOS_SERVICE_PORT_INDEX` will not impact the cache refresh.
        """
        bad_app = _marathon_container_network_nginx_app(port_index=1)
        with dcos_api_session.marathon.deploy_and_cleanup(bad_app, check_health=False, timeout=120):

            with pytest.raises(AssertionError):
                _wait_for_state_cache_refresh(dcos_api_session, bad_app['id'])

            good_app = _marathon_container_network_nginx_app(port_index=0)
            with dcos_api_session.marathon.deploy_and_cleanup(good_app, check_health=False, timeout=120):
                _wait_for_state_cache_refresh(dcos_api_session, good_app['id'])


@retry(
    stop_max_delay=30000,
    wait_fixed=2000,
    retry_on_exception=lambda e: isinstance(e, AssertionError),
)
def _wait_for_state_cache_refresh(dcos_api_session: DcosApiSession, service: str) -> None:
    result = dcos_api_session.get('/service{}'.format(service), timeout=2)
    assert result.status_code == 200


def _marathon_container_network_nginx_app(port_index: int = 0) -> dict:
    app_id = str(uuid.uuid4())
    app_definition = {
        'id': '/nginx-{}'.format(app_id),
        'cpus': 0.1,
        'instances': 1,
        'mem': 64,
        'networks': [{'mode': 'container/bridge'}],
        'requirePorts': False,
        'labels': {
            'DCOS_SERVICE_NAME': 'nginx-{}'.format(app_id),
            'DCOS_SERVICE_SCHEME': 'http',
            'DCOS_SERVICE_PORT_INDEX': str(port_index),
        },
        'container': {
            'type': 'DOCKER',
            'docker': {
                'image': 'bitnami/nginx:latest',
                'forcePullImage': True,
                'privileged': False,
                'parameters': []
            },
            'portMappings': [
                {
                    'containerPort': 8080,
                    'labels': {
                        'VIP_0': '/nginx-{}:8080'.format(app_id),
                    },
                    'protocol': 'tcp',
                    'name': 'http',
                }
            ]
        }
    }
    return app_definition
