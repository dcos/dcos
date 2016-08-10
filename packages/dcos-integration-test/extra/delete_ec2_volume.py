#!/usr/bin/env python3
import contextlib
import logging
import os
import sys

import boto3
import botocore
import requests
import retrying


@contextlib.contextmanager
def _remove_env_vars(*env_vars):
    environ = dict(os.environ)

    for env_var in env_vars:
        try:
            del os.environ[env_var]
        except KeyError:
            pass

    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(environ)


def delete_ec2_volume(name, timeout=300):
    """Delete an EC2 EBS volume by its "Name" tag

    Args:
        timeout: seconds to wait for volume to become available for deletion

    """
    @retrying.retry(wait_fixed=30 * 1000, stop_max_delay=timeout * 1000,
                    retry_on_exception=lambda exc: isinstance(exc, botocore.exceptions.ClientError))
    def _delete_volume(volume):
        volume.delete()  # Raises ClientError if the volume is still attached.

    def _get_current_aws_region():
        try:
            return requests.get('http://169.254.169.254/latest/meta-data/placement/availability-zone').text.strip()[:-1]
        except requests.RequestException as ex:
            logging.warning("Can't get AWS region from instance metadata: {}".format(ex))
            return None

    # Remove AWS environment variables to force boto to use IAM credentials.
    with _remove_env_vars('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'):
        volumes = list(boto3.session.Session(
            # We assume we're running these tests from a cluster node, so we
            # can assume the region for the instance on which we're running is
            # the same region in which any volumes were created.
            region_name=_get_current_aws_region(),
        ).resource('ec2').volumes.filter(Filters=[{'Name': 'tag:Name', 'Values': [name]}]))

    if len(volumes) == 0:
        raise Exception('no volumes found with name {}'.format(name))
    elif len(volumes) > 1:
        raise Exception('multiple volumes found with name {}'.format(name))
    volume = volumes[0]

    try:
        _delete_volume(volume)
    except retrying.RetryError as ex:
        raise Exception('Operation was not completed within {} seconds'.format(timeout)) from ex


if __name__ == '__main__':
    delete_ec2_volume(sys.argv[1])
