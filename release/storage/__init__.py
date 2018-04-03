import abc
import os.path

from pkgpanda.util import make_directory


class UnsupportedOperation(RuntimeError):
    pass


class AbstractStorageProvider(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def copy(self,
             source_path,
             destination_path):
        """Copy the file and all metadata from destination_path to source_path."""
        pass

    @abc.abstractmethod
    def upload(self,
               destination_path,
               blob=None,
               local_path=None,
               no_cache=None,
               content_type=None):
        """Upload to destinoation_path the given blob or local_path, attaching metadata for additional properties."""
        pass

    # TODO(cmaloney): Add test for download, download_if_not_exist
    @abc.abstractmethod
    def download_inner(self, path, local_path):
        pass

    def download(self, path, local_path):
        dirname = os.path.dirname(local_path)
        if dirname:
            make_directory(dirname)
        self.download_inner(path, local_path)

    def download_if_not_exist(self, path, local_path):
        if os.path.exists(local_path):
            return

        self.download(path, local_path)

    @abc.abstractmethod
    def exists(self, path):
        """Return true iff the given file / path exists."""
        pass

    @abc.abstractmethod
    def fetch(self, path):
        """Download the given file and return bytes. Do not use on large files.

        Throw an exception if the path doesn't exist or is a folder."""
        pass

    @abc.abstractmethod
    def remove_recursive(self, path):
        """Recursively remove the given path. Should never error / always complete successfully.

        If the given path doesn't exist then just ignore and keep going.
        If the given path is a folder, delete all files and folders within it.
        If the given path is a file, delete the file and return."""
        pass

    @abc.abstractmethod
    def list_recursive(self, folder):
        """Return a set of the contents of the given folder and every subfolder with no metadata.

        Should return a set of filenames with the given folder prefix included.

        In a bucket containing blobs with the prefixes: bar, b/baz a/foo, a/folder/a, a/folder/b
        a call to list_recursive(a) would return: {"a/foo", "a/folder/a", "a/folder/b"}

        If given a file instead of a folder the behavior is unspecified."""
        pass

    @abc.abstractproperty
    def url(self):
        """The base url which should be used to fetch resources from this storage provider"""
        pass

    @property
    def read_only(self):
        """Returns true if no write operations (upload, copy, remove) may be done on this storage provider."""
        return False


class ReadOnlyProxy(AbstractStorageProvider):
    def __init__(self, storage_provider: AbstractStorageProvider):
        self._storage_provider = storage_provider

    def copy(self,
             source_path,
             destination_path):
        raise UnsupportedOperation("copy on read-only storage")

    def upload(self,
               destination_path,
               blob=None,
               local_path=None,
               no_cache=None,
               content_type=None):
        raise UnsupportedOperation("upload on read-only storage")

    def download(self, path, local_path):
        return self._storage_provider.download(path, local_path)

    def exists(self, path):
        return self._storage_provider.exists(path)

    def fetch(self, path):
        return self._storage_provider.fetch(path)

    def remove_recursive(self, path):
        raise UnsupportedOperation("remove_recursive on read-only storage")

    def list_recursive(self, folder):
        raise UnsupportedOperation()

    def url(self):
        return self._storage_provider.url(self)

    @property
    def read_only(self):
        return True
