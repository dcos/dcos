import boto3
import botocore

from release.storage import AbstractStorageProvider


def get_session(boto3_profile=None, region_name=None, access_key_id=None, secret_access_key=None):
        if boto3_profile:
            if access_key_id or secret_access_key or region_name:
                raise ValueError("access_key_id, secret_access_key, and region_name cannot be used with boto3_profile")
            return boto3.session.Session(profile_name=boto3_profile)
        elif access_key_id or secret_access_key or region_name:
            if not access_key_id or not secret_access_key or not region_name:
                raise ValueError("access_key_id, secret_access_key, and region_name must all be set")
            return boto3.session.Session(
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name=region_name)
        else:
            raise ValueError("boto_profile or explicit AWS credentials (access_key_id, "
                             "secret_access_key, region_name) must be provided")


class S3StorageProvider(AbstractStorageProvider):
    name = 'aws'

    def __init__(self, bucket, object_prefix, download_url, boto3_profile=None, region_name=None,
                 access_key_id=None, secret_access_key=None):
        if object_prefix is not None:
            assert object_prefix and not object_prefix.startswith('/') and not object_prefix.endswith('/')

        self.__session = get_session(boto3_profile, region_name, access_key_id, secret_access_key)
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

        new_object.copy_from(CopySource=old_path)

    def upload(self,
               destination_path,
               blob=None,
               local_path=None,
               no_cache=None,
               content_type=None):
        extra_args = {}
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
