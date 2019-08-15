

class ValidationError(Exception):
    def __init__(self, errors, unset):
        self.errors = errors
        self.unset = unset
        super().__init__(str(errors), str(unset))

    def __str__(self):
        return "<ValidationError errors: {}; unset: {}".format(self.errors, self.unset)

    def __repr__(self):
        return self.__str__()


class ExhibitorTLSBootstrapError(Exception):
    def __init__(self, errors):
        self.errors = errors

    def __str__(self):
        return "<ExhibitorTLSBootstrapError errors: {}>".format(', '.join(self.errors))

    def __repr__(self):
        return self.__str__()
