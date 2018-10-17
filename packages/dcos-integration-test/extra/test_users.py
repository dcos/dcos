"""
A collection of tests covering user management in DC/OS.

Assume that access control is activated in Master Admin Router (could be
disabled with `oauth_enabled`) and therefore authenticate individual HTTP
requests.

One aspect of DC/OS user management is that once authenticated a user can add
other users. Unauthenticated HTTP requests are rejected by Master Admin Router
and user management fails (this is the coarse-grained authorization model of
(open) DC/OS). Here, test that unauthenticated HTTP requests cannot manage
users. However, do not test that newly added users can add other users: in this
test suite we are limited to having authentication state for just a single user
available. This is why we can test managing other users only from that first
user's point of view. That is, we can not test that a user (e.g. user2) which
was added by the first user (user1) can add another user (user3).
"""
import logging

import pytest

from test_helpers import expanded_config


__maintainer__ = 'jgehrcke'
__contact__ = 'security-team@mesosphere.io'


log = logging.getLogger(__name__)


# Skip entire module in downstream integration tests.
if 'security' in expanded_config:
    pytest.skip(
        'Skip upstream-specific user management tests',
        allow_module_level=True
    )


def get_users(apisession):
    r = apisession.get('/acs/api/v1/users')
    r.raise_for_status()
    users = {u['uid']: u for u in r.json()['array']}
    return users


def delete_user(apisession, uid):
    r = apisession.delete('/acs/api/v1/users/%s' % (uid, ))
    r.raise_for_status()
    assert r.status_code == 204


@pytest.fixture()
def remove_users_added_by_test(dcos_api_session):
    users_before = set(get_users(dcos_api_session))
    log.info('remove_users_added_by_test pre test: users are %s', users_before)
    try:
        yield
    finally:
        users_after = set(get_users(dcos_api_session))
        new_uids = users_after - users_before
        for uid in new_uids:
            log.info('remove_users_added_by_test post test: remove `%s`', uid)
            delete_user(dcos_api_session, uid)


def test_users_get(dcos_api_session):
    users = get_users(dcos_api_session)
    assert users

    required_keys = ('uid', 'description')
    for _, userdict in users.items():
        for k in required_keys:
            assert k in userdict


def test_user_put_no_email_uid(dcos_api_session):
    r = dcos_api_session.put('/acs/api/v1/users/user1')

    # This is the current behavior. It does not need to stay in future versions.
    assert r.status_code == 500
    assert 'invalid email' in r.text


@pytest.mark.usefixtures('remove_users_added_by_test')
def test_user_put_email_uid(dcos_api_session):
    # The current behavior is that the request body can be an empty JSON
    # document. It does not need to stay in future versions.
    r = dcos_api_session.put('/acs/api/v1/users/user1@email.de', json={})
    r.raise_for_status()
    assert r.status_code == 201

    users = get_users(dcos_api_session)
    assert len(users) > 1
    assert 'user1@email.de' in users


@pytest.mark.usefixtures('remove_users_added_by_test')
def test_user_put_optional_payload(dcos_api_session):
    # This is the current behavior. It does not need to stay in future versions.

    r = dcos_api_session.put(
        '/acs/api/v1/users/user2@email.de',
        json={'creator_uid': 'any@thing.bla', 'cluster_url': 'foobar'}
    )
    assert r.status_code == 201, r.text

    r = dcos_api_session.put(
        '/acs/api/v1/users/user3@email.de',
        json={'creator_uid': 'any@thing.bla', 'description': 'barfoo'}
    )
    assert r.status_code == 201, r.text

    r = dcos_api_session.put(
        '/acs/api/v1/users/user4@email.de',
        json={'is_remote': False}
    )
    assert r.status_code == 201, r.text


@pytest.mark.usefixtures('remove_users_added_by_test')
def test_user_conflict(dcos_api_session):
    # This is the current behavior. It does not need to stay in future versions.

    r = dcos_api_session.put(
        '/acs/api/v1/users/user2@email.de',
        json={'creator_uid': 'any@thing.bla', 'cluster_url': 'foobar'}
    )
    assert r.status_code == 201, r.text

    r = dcos_api_session.put(
        '/acs/api/v1/users/user2@email.de',
        json={'creator_uid': 'any@thing.bla', 'cluster_url': 'foobar'}
    )
    assert r.status_code == 409, r.text


@pytest.mark.usefixtures('remove_users_added_by_test')
def test_user_delete(dcos_api_session):
    r = dcos_api_session.put('/acs/api/v1/users/user6@email.de', json={})
    r.raise_for_status()
    assert r.status_code == 201

    r = dcos_api_session.delete('/acs/api/v1/users/user6@email.de')
    r.raise_for_status()
    assert r.status_code == 204

    users = get_users(dcos_api_session)
    assert 'user6@email.de' not in users


def test_user_put_requires_authentication(noauth_api_session):
    r = noauth_api_session.put('/acs/api/v1/users/user7@email.de', json={})
    assert r.status_code == 401, r.text


def test_dynamic_ui_config(dcos_api_session):
    r = dcos_api_session.get('/dcos-metadata/ui-config.json')
    data = r.json()
    assert not data['clusterConfiguration']['firstUser']
    assert 'id' in data['clusterConfiguration']
    assert 'uiConfiguration' in data
