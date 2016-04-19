import os

import requests

from release.storage import AbstractStorageProvider


class HttpStorageProvider(AbstractStorageProvider):
    name = 'http'

    def __init__(self, url):
        self.__url = url.rstrip('/') + '/'

    def _get_absolute(self, path):
        assert not path.startswith('/')
        return self.__url + path

    def copy(self,
             source_path,
             destination_path):
        raise NotImplementedError()

    def upload(self,
               destination_path,
               blob=None,
               local_path=None,
               no_cache=None,
               content_type=None):
        raise NotImplementedError()

    def download_inner(self, path, local_path):
        local_path_tmp = '{}.tmp'.format(local_path)
        url = self._get_absolute(path)
        try:
            with open(local_path_tmp, 'w+b') as f:
                r = requests.get(url, stream=True)
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=4096):
                    f.write(chunk)
                os.rename(local_path_tmp, local_path)
        except:
            # Delete the temp file, re-raise.
            try:
                os.remove(local_path_tmp)
            except Exception:
                pass
        self.get_object(path).download_file(local_path)

    def exists(self, path):
        url = self._get_absolute(path)

        # TODO(cmaloney): 200 is overly restrictive here... After hitting more
        # webservers expand to include other common / valid status codes that
        # indicate resource is found / exists.
        return requests.head(url=url).status_code == 200

    def fetch(self, path):
        r = requests.get(url=self._get_absolute(path))
        r.raise_for_status()
        return r.body

    def remove_recursive(self, path):
        raise NotImplementedError()

    def list_recursive(self, path):
        raise NotImplementedError()

    @property
    def url(self):
        return self.__url

    @property
    def read_only(self):
        return True

factories = {
    'read': HttpStorageProvider
}
