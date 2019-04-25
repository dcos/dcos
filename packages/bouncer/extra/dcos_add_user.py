#!/usr/bin/env python
"""
This script adds remote users in DC/OS IAM for the Auth0 identity provider.
"""

import argparse
import logging
import re

import requests


log = logging.getLogger(__name__)
logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')


# To keep this script simple and avoid authentication and authorization this
# script uses local IAM address instead of going through Admin Router
IAM_BASE_URL = 'http://127.0.0.1:8101'


def add_user(uid: str) -> None:

    url = '{iam}/acs/api/v1/users/{uid}'.format(
        iam=IAM_BASE_URL,
        uid=uid,
    )
    r = requests.put(url, json={
        'provider_type': 'oidc',
        'provider_id': 'https://dcos.auth0.com/'
        }
    )

    # The 409 response code means that user already exists in the DC/OS IAM
    # service
    if r.status_code == 409:
        log.info('User `%s` already exists', uid)
        return
    r.raise_for_status()
    log.info('Created IAM user `%s`', uid)


def main() -> None:
    """
    Add user to database with email argument as the user ID.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'email',
        type=str,
        help='E-mail address of the user to be added',
    )
    args = parser.parse_args()

    """The `args.email` in fact must look like an email address,
    otherwise the HTTP request to Bouncer will fail.
    """
    email = args.email
    if re.match(r'[^@]+@[^@]+\.[^@]+', email):
        add_user(email)
    else:
        log.error('Provided uid `%s` does not appear to be an email address', email)


if __name__ == "__main__":
    main()
