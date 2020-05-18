"""
A collection of tests covering legacy user management in DC/OS.

Legacy user management is considered to be the user management API offered by
`dcos-oauth` up to DC/OS release 1.12.

Assume that access control is activated in Master Admin Router (could be
disabled with `oauth_enabled`) and therefore authenticate individual HTTP
dcos_api_session.

One aspect of legacy DC/OS user management is that once authenticated a user can
add other users. Unauthenticated HTTP dcos_api_session are rejected by Master
Admin Router and user management fails (this is the coarse-grained authorization
model of (open) DC/OS). Here, test that unauthenticated HTTP dcos_api_session
cannot manage users. However, do not test that newly added users can add other
users: in this test suite we are limited to having authentication state for just
a single user available. This is why we can test managing other users only from
that first user's point of view. That is, we can not test that a user (e.g.
user2) which was added by the first user (user1) can add another user (user3).
"""
import logging
import uuid

from typing import Generator

import pytest

from dcos_test_utils.dcos_api import DcosApiSession
from dcos_test_utils.dcos_cli import DcosCli
from test_helpers import get_expanded_config


__maintainer__ = 'jgehrcke'
__contact__ = 'security-team@mesosphere.io'


log = logging.getLogger(__name__)


# Skip entire module in downstream integration tests.
@pytest.fixture(autouse=True)
def skip_in_downstream() -> None:
    expanded_config = get_expanded_config()
    if 'security' in expanded_config:
        pytest.skip(
            'Skip upstream-specific user management tests',
            allow_module_level=True
        )


def get_users(dcos_api_session: DcosApiSession) -> dict:
    r = dcos_api_session.get('/acs/api/v1/users')
    r.raise_for_status()
    users = {u['uid']: u for u in r.json()['array']}
    return users


def delete_user(dcos_api_session: DcosApiSession, uid: str) -> None:
    r = dcos_api_session.delete('/acs/api/v1/users/%s' % (uid, ))
    r.raise_for_status()
    assert r.status_code == 204


@pytest.fixture()
def remove_users_added_by_test(dcos_api_session: DcosApiSession) -> Generator:
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


def test_users_get(dcos_api_session: DcosApiSession) -> None:
    users = get_users(dcos_api_session)
    assert users

    required_keys = ('uid', 'description')
    for userdict in users.values():
        for k in required_keys:
            assert k in userdict


def test_user_put_no_email_uid_empty_body(dcos_api_session: DcosApiSession) -> None:
    # This test mainly demonstrates a subtle API difference between dcos-oauth
    # (legacy) and Bouncer.
    r = dcos_api_session.put('/acs/api/v1/users/user1')

    # This is the old behavior in dcos-oauth.
    # assert r.status_code == 500
    # assert 'invalid email' in r.text

    # With Bouncer non-email uids are valid, and the request fails as of the
    # missing request body.
    assert r.status_code == 400
    assert 'Request has bad Content-Type or lacks JSON data' in r.text


@pytest.mark.usefixtures('remove_users_added_by_test')
def test_legacy_user_creation_with_empty_json_doc(dcos_api_session: DcosApiSession) -> None:
    # Legacy HTTP clients built for dcos-oauth such as the web UI (up to DC/OS
    # 1.12) might insert users in the following way: uid appears to be an email
    # address, and the JSON document in the request body does not provide a
    # `public_key` or a `password` property (indicating local user), or is
    # empty. The legacy web UI would insert users like that and expect those
    # users to be remote users, usable with the legacy OIDC ID Token login
    # method through the 'https://dcos.auth0.com/' provider. This behavior is
    # maintained in Bouncer for backwards compatibility.
    r = dcos_api_session.put('/acs/api/v1/users/user@domain.foo', json={})
    assert r.status_code == 201, r.text

    # Bouncer annotates the created user (this is new compared to dcos-oauth).
    r = dcos_api_session.get('/acs/api/v1/users/user@domain.foo')
    assert r.json()['provider_type'] == 'oidc'
    assert r.json()['provider_id'] == 'https://dcos.auth0.com/'
    assert r.json()['is_remote'] is True

    # When the uid however does not appear to be an email address the more sane
    # behavior of Bouncer takes effect: an empty (meaningless) JSON body
    # results in a useful error message.
    r = dcos_api_session.put('/acs/api/v1/users/user1', json={})
    assert r.status_code == 400
    assert 'One of `password` or `public_key` must be provided' in r.text


@pytest.mark.usefixtures('remove_users_added_by_test')
def test_user_put_email_uid_and_description(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.put(
        '/acs/api/v1/users/user1@domain.foo',
        json={'description': 'integration test user'}
    )
    assert r.status_code == 201, r.text

    users = get_users(dcos_api_session)
    assert len(users) > 1
    assert 'user1@domain.foo' in users


@pytest.mark.usefixtures('remove_users_added_by_test')
def test_user_put_with_legacy_body(dcos_api_session: DcosApiSession) -> None:
    # The UI up to DC/OS 1.12 sends the `creator_uid` and the `cluster_url`
    # properties although they are not used by dcos-oauth. Bouncer supports
    # these two properties for legacy reasons. Note(JP): As a follow-up task we
    # should change the UI to not send these properties anymore, and then remove
    # the properties from Bouncer's UserCreate JSON schema again, ideally within
    # the 1.13 development cycle.
    r = dcos_api_session.put(
        '/acs/api/v1/users/user2@domain.foo',
        json={'creator_uid': 'any@thing.bla', 'cluster_url': 'foobar'}
    )
    assert r.status_code == 201, r.text


@pytest.mark.usefixtures('remove_users_added_by_test')
def test_user_conflict(dcos_api_session: DcosApiSession) -> None:
    # Note: the empty request body is not the decisive criterion here.
    r = dcos_api_session.put('/acs/api/v1/users/user2@domain.foo', json={})
    assert r.status_code == 201, r.text

    r = dcos_api_session.put('/acs/api/v1/users/user2@domain.foo', json={})
    assert r.status_code == 409, r.text


@pytest.mark.usefixtures('remove_users_added_by_test')
def test_user_delete(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.put('/acs/api/v1/users/user6@domain.foo', json={})
    r.raise_for_status()
    assert r.status_code == 201

    r = dcos_api_session.delete('/acs/api/v1/users/user6@domain.foo')
    r.raise_for_status()
    assert r.status_code == 204

    users = get_users(dcos_api_session)
    assert 'user6@domain.foo' not in users


def test_user_put_requires_authentication(noauth_api_session: DcosApiSession) -> None:
    r = noauth_api_session.put('/acs/api/v1/users/user7@domain.foo', json={})
    assert r.status_code == 401, r.text


def test_dynamic_ui_config(dcos_api_session: DcosApiSession) -> None:
    r = dcos_api_session.get('/dcos-metadata/ui-config.json')
    data = r.json()
    assert not data['clusterConfiguration']['firstUser']
    assert 'id' in data['clusterConfiguration']
    assert 'uiConfiguration' in data


def test_dcos_add_user(dcos_api_session: DcosApiSession, new_dcos_cli: DcosCli) -> None:
    """
    dcos_add_user.py script adds a user to IAM using the
    script dcos_add_user.py.
    """

    email_address = uuid.uuid4().hex + '@example.com'
    command = ['python', '/opt/mesosphere/bin/dcos_add_user.py', email_address]
    new_dcos_cli.exec_command(command)

    try:
        r = dcos_api_session.get('/acs/api/v1/users')
        r.raise_for_status()
        expected_user_data = {
            "uid": email_address,
            "description": "",
            "url": "/acs/api/v1/users/" + email_address,
            "is_remote": True,
            "is_service": False,
            "provider_type": "oidc",
            "provider_id": "https://dcos.auth0.com/"
        }
        assert expected_user_data in r.json()['array']
    finally:
        delete_user(dcos_api_session, email_address)


def test_check_message_on_adding_user_twice(dcos_api_session: DcosApiSession, new_dcos_cli: DcosCli) -> None:
    """
    Check that the correct message is emitted on adding the
    same user for the second time.
    """

    email_address = uuid.uuid4().hex + '@example.com'
    command = ['python', '/opt/mesosphere/bin/dcos_add_user.py', email_address]
    stdout, stderr = new_dcos_cli.exec_command(command)

    try:
        expected_output = '[INFO] Created IAM user `' + email_address + '`\n'
        assert '' == stdout
        assert expected_output == stderr

        stdout, stderr = new_dcos_cli.exec_command(command)
        expected_error = '[INFO] User `' + email_address + '` already exists\n'
        assert expected_error == stderr
        assert '' == stdout
    finally:
        delete_user(dcos_api_session, email_address)
