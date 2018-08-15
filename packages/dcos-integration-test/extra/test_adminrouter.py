__maintainer__ = 'jgehrcke'
__contact__ = 'dcos-security@mesosphere.io'


def test_adminrouter_supports_gzip(dcos_api_session):
    # Confirm that Master Admin Router offers gzip compression
    # for requesting .html and .js files (the MIME types
    # associated with them). It should also offer it for
    # more MIME types, such as for CSS and others. The
    # goal of this test however is is not to have complete
    # coverage.
    r = dcos_api_session.get('/index.html')
    assert r.headers['Content-Encoding'] == 'gzip'

    r = dcos_api_session.get('/index.js')
    assert r.headers['Content-Encoding'] == 'gzip'
