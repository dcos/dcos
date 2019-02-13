import pytest


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
    def test_redirect_host(
        self,
        dcos_api_session,
        path,
        expected,
    ) -> None:
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
