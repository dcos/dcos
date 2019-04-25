import pytest
import requests


class TestRedirect:

    @pytest.mark.parametrize(
        'path', ('/mesos_dns', '/net', '/exhibitor', '/mesos')
    )
    def test_redirect(self, master_ar_process, valid_user_header, path):
        """
        URL's with no slash on end may redirect to the same URL with a
        slash appended. If this redirection uses the Host header to write
        the redirection, then it is susceptible to a client being tricked
        into setting the Host header to a bad host, and then redirecting
        the request (including an Authorization header) to the bad host.
        """
        url = master_ar_process.make_url_from_path(path)
        headers = valid_user_header.copy()
        headers['Host'] = 'bad.host'
        resp = requests.get(
            url,
            allow_redirects=False,
            headers=headers
            )
        resp.raise_for_status()

        if resp.status_code in (301, 302, 303, 307):
            assert 'bad.host' not in resp.headers['Location']
        else:
            assert resp.status_code == 200
