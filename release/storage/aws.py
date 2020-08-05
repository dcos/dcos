from typing import Optional

import boto3
import botocore

from release.storage import AbstractStorageProvider


def get_aws_session(access_key_id, secret_access_key, region_name=None):
    """ This method will replace access_key_id and secret_access_key
    with None if one is set to '' This allows falling back to the AWS internal
    logic so that one of the following options can be used:
    http://boto3.readthedocs.io/en/latest/guide/configuration.html#configuring-credentials

    This is needed by dcos_installer/backend.py which does AWS actions using
    explicit credentials. The process is ran from the dcos_generate_config.sh
    artifact docker container, which can interfere with the usual boto3 credential method.
    The gen library only uses empty strings to denote unset, which does not work for boto3
    """
    if not access_key_id:
        access_key_id = None
    if not secret_access_key:
        secret_access_key = None
    return boto3.session.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region_name)


class S3StorageProvider(AbstractStorageProvider):
    name = 'aws'

    def __init__(self, bucket, object_prefix, download_url,
                 access_key_id=None, secret_access_key=None, region_name=None):
        """ If access_key_id and secret_acccess_key are unset, boto3 will
        try to authenticate by other methods. See here for other credential options:
        http://boto3.readthedocs.io/en/latest/guide/configuration.html#configuring-credentials
        """
        if object_prefix is not None:
            assert object_prefix and not object_prefix.startswith('/') and not object_prefix.endswith('/')

        self.__session = get_aws_session(access_key_id, secret_access_key, region_name)
        self.__bucket = self.__session.resource('s3').Bucket(bucket)
        self.__object_prefix = object_prefix
        self.__url = download_url

    @property
    def object_prefix(self):
        if self.__object_prefix is None:
            return ''
        return self.__object_prefix + '/'

    def _get_path(self, name):

        return self.object_prefix + name

    def _get_objects_with_prefix(self, prefix):
        return self.__bucket.objects.filter(Prefix=self._get_path(prefix))

    def get_object(self, name):
        assert not name.startswith('/')
        return self.__bucket.Object(self._get_path(name))

    def fetch(self, path):
        body = self.get_object(path).get()['Body']
        data = bytes()
        for chunk in iter(lambda: body.read(4096), b''):
            data += chunk
        return data

    def download_inner(self, path, local_path):
        self.get_object(path).download_file(local_path)

    @property
    def url(self):
        return self.__url

    def copy(self, source_path, destination_path):
        src_object = self.get_object(source_path)
        new_object = self.get_object(destination_path)
        old_path = src_object.bucket_name + '/' + src_object.key

        new_object.copy_from(CopySource=old_path, ACL='bucket-owner-full-control')

    def upload(self,
               destination_path: str,
               blob: Optional[bytes]=None,
               local_path: Optional[str]=None,
               no_cache: bool=False,
               content_type: Optional[str]=None):
        extra_args = {}
        extra_args['ACL'] = 'bucket-owner-full-control'
        if no_cache:
            extra_args['CacheControl'] = 'no-cache'
        if content_type:
            extra_args['ContentType'] = content_type

        s3_object = self.get_object(destination_path)

        assert local_path is None or blob is None
        if local_path:
            with open(local_path, 'rb') as data:
                s3_object.put(Body=data, **extra_args)
        else:
            assert isinstance(blob, bytes)
            s3_object.put(Body=blob, **extra_args)

    def exists(self, path):
        try:
            self.get_object(path).load()
            return True
        except botocore.client.ClientError:
            return False

    def list_recursive(self, path):
        prefix_len = len(self.object_prefix)
        names = set()
        for object_summary in self._get_objects_with_prefix(path):
            name = object_summary.key

            # Sanity check the prefix is there before removing.
            assert name.startswith(self.__object_prefix + '/')

            # Add the unprefixed name since the caller of this function doesn't
            # know we've added the prefix / only sees inside the prefix ever.
            names.add(name[prefix_len:])

        return names

    def remove_recursive(self, path):
        for obj in self._get_objects_with_prefix(path):
            obj.delete()


factories = {
    "s3": S3StorageProvider
}
