import subprocess

import pytest


@pytest.fixture(scope='module')
def noauth_cluster(cluster):
    return cluster.get_user_session(None)


def auth_enabled():
    out = subprocess.check_output([
        '/bin/bash', '-c',
        'source /opt/mesosphere/etc/adminrouter.env && echo $ADMINROUTER_ACTIVATE_AUTH_MODULE']).\
        decode().strip('\n')
    assert out in ['true', 'false'], 'Unknown ADMINROUTER_ACTIVATE_AUTH_MODULE state: {}'.format(out)
    return out == 'true'


@pytest.mark.skipif(not auth_enabled(),
                    reason='Can only test adminrouter enforcement if auth is enabled')
def test_adminrouter_access_control_enforcement(cluster, noauth_cluster):
    r = noauth_cluster.get('/acs/api/v1')
    assert r.status_code == 401
    assert r.headers['WWW-Authenticate'] in ('acsjwt', 'oauthjwt')
    # Make sure that this is UI's error page body,
    # including some JavaScript.
    assert '<html>' in r.text
    assert '</html>' in r.text
    assert 'window.location' in r.text
    # Verify that certain locations are forbidden to access
    # when not authed, but are reachable as superuser.
    for path in ('/mesos_dns/v1/config', '/service/marathon/', '/mesos/'):
        r = noauth_cluster.get(path)
        assert r.status_code == 401
        r = cluster.get(path)
        assert r.status_code == 200

    # Test authentication with auth cookie instead of Authorization header.
    authcookie = {
        'dcos-acs-auth-cookie': cluster.web_auth_default_user.auth_cookie}
    r = noauth_cluster.get(
        '/service/marathon/',
        cookies=authcookie)
    assert r.status_code == 200


def test_logout(cluster):
    """Test logout endpoint. It's a soft logout, instructing
    the user agent to delete the authentication cookie, i.e. this test
    does not have side effects on other tests.
    """
    r = cluster.get('/acs/api/v1/auth/logout')
    cookieheader = r.headers['set-cookie']
    assert 'dcos-acs-auth-cookie=;' in cookieheader or 'dcos-acs-auth-cookie="";' in cookieheader
    assert 'expires' in cookieheader.lower()
