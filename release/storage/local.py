import os.path
from typing import Optional

from pkgpanda.util import copy_file, is_absolute_path, make_directory, remove_directory
from release.storage import AbstractStorageProvider


# Local storage provider useful for testing. Not used for the local artifacts
# since it would cause excess / needless copies, and doesn't work for "promote"
# since the artifacts won't be local (And downloading them all to be local
# would be a significant time sink).
class LocalStorageProvider(AbstractStorageProvider):
    name = 'local_storage_provider'

    def __init__(self, path: str):
        assert not path.endswith('/')
        self.__storage_path = path

    def __full_path(self, path):
        return self.__storage_path + '/' + path

    def fetch(self, path):
        with open(self.__full_path(path), 'rb') as f:
            return f.read()

    def download_inner(self, path, local_path):
        copy_file(self.__full_path(path), local_path)

    # Copy between fully qualified paths
    def __copy(self, full_source_path, full_destination_path):
        make_directory(os.path.dirname(full_destination_path))
        copy_file(full_source_path, full_destination_path)

    def copy(self, source_path, destination_path):
        self.__copy(self.__full_path(source_path), self.__full_path(destination_path))

    def upload(
            self,
            destination_path: str,
            blob: Optional[bytes]=None,
            local_path: Optional[str]=None,
            no_cache: bool=False,
            content_type: Optional[str]=None):
        # TODO(cmaloney): Don't discard the extra no_cache / content_type. We ideally want to be
        # able to test those are set.
        destination_full_path = self.__full_path(destination_path)
        make_directory(os.path.dirname(destination_full_path))

        assert local_path is None or blob is None
        if local_path:
            self.__copy(local_path, destination_full_path)
        else:
            assert isinstance(blob, bytes)
            with open(destination_full_path, 'wb') as f:
                f.write(blob)

    def exists(self, path):
        assert not is_absolute_path(path)
        return os.path.exists(self.__full_path(path))

    def remove_recursive(self, path):
        full_path = self.__full_path(path)

        # Make sure we're not going to delete something too horrible / in the
        # base system. Adjust as needed.
        assert len(path) > 5
        assert len(full_path) > 5
        remove_directory(full_path)

    def list_recursive(self, path):
        final_filenames = set()
        for dirpath, _, filenames in os.walk(self.__full_path(path)):
            assert dirpath.startswith(self.__storage_path)
            dirpath_no_prefix = dirpath[len(self.__storage_path) + 1:]
            for filename in filenames:
                final_filenames.add(dirpath_no_prefix + '/' + filename)

        return final_filenames

    @property
    def url(self):
        return 'file://' + self.__storage_path + '/'


factories = {
    'path': LocalStorageProvider
}
