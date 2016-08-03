class FetchError(Exception):

    def __init__(self, url, out_filename, base_exception, rm_failed):
        self.url = url
        self.out_filename = out_filename
        self.base_exception = base_exception
        self.rm_failed = rm_failed

    def __str__(self):
        msg = "Problem fetching {} to {} because of {}.".format(self.url, self.out_filename, self.base_exception)

        if self.rm_failed:
            msg += " Unable to remove partial download. Future builds may have problems because of it.".format(
                self.rm_failed)

        return msg


class InstallError(Exception):
    pass


class PackageError(Exception):
    pass


class PackageNotFound(PackageError):
    pass


class ValidationError(Exception):
    pass
