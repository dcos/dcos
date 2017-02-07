from typing import Optional

import azure.storage.blob
import requests
from retrying import retry

from release.storage import AbstractStorageProvider


class AzureBlockBlobStorageProvider(AbstractStorageProvider):
    name = 'azure'

    def __init__(self, account_name, account_key, container, download_url):
        assert download_url.endswith('/')
        self.container = container
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        self.blob_service = azure.storage.blob.BlockBlobService(account_name=account_name,
                                                                account_key=account_key,
                                                                request_session=session)
        self.__url = download_url

    @property
    def url(self):
        return self.__url

    def copy(self, source_path, destination_path):
        assert destination_path[0] != '/'
        az_blob_url = self.blob_service.make_blob_url(self.container, source_path)

        # NOTE(cmaloney): The try / except on copy exception is ugly, but seems
        # to be necessary since sometimes we end up with hanging copy operations.
        resp = None
        try:
            resp = self.blob_service.copy_blob(self.container, destination_path, az_blob_url)
        except azure.common.AzureConflictHttpError:
            # Cancel the past copy, make a new copy
            properties = self.blob_service.get_blob_properties(self.container, destination_path)
            assert properties.id
            self.blob_service.abort_copy_blob(self.container, destination_path, properties.id)

            # Try the copy again
            resp = self.blob_service.copy_blob(self.container, destination_path, az_blob_url)

        # Since we're copying inside of one bucket the copy should always be
        # synchronous and successful.
        assert resp.status == 'success'

    @retry(stop_max_attempt_number=3)
    def upload(self,
               destination_path: str,
               blob: Optional[bytes]=None,
               local_path: Optional[str]=None,
               no_cache: bool=False,
               content_type: Optional[str]=None):
        content_settings = azure.storage.blob.ContentSettings()

        if no_cache:
            content_settings.cache_control = None
        if content_type:
            content_settings.content_type = content_type

        # Must be a local_path or blob upload, not both
        assert local_path is None or blob is None
        if local_path:
            # Upload local_path
            self.blob_service.create_blob_from_path(
                self.container,
                destination_path,
                local_path,
                content_settings=content_settings,
                max_connections=16)
        else:
            assert blob is not None
            self.blob_service.create_blob_from_text(
                self.container,
                destination_path,
                blob,
                content_settings=content_settings,
                max_connections=16)

    def exists(self, path):
        try:
            self.blob_service.get_blob_properties(self.container, path)
            return True
        except azure.common.AzureMissingResourceHttpError:
            return False

    def fetch(self, path):
        return self.blob_service.get_blob_to_bytes(self.container, path).content

    def download_inner(self, path, local_path):
        return self.blob_service.get_blob_to_path(self.container, path, local_path)

    def list_recursive(self, path):
        names = set()
        for blob in self.blob_service.list_blobs(self.container, path):
            names.add(blob.name)
        return names

    def remove_recursive(self, path):
        for blob_name in self.list_recursive(path):
            self.blob_service.delete_blob(self.container, blob_name)


factories = {
    "block_blob": AzureBlockBlobStorageProvider
}
