

class ValidationError(Exception):
    def __init__(self, errors, unset):
        self.errors = errors
        self.unset = unset
        super().__init__(str(errors), str(unset))

    def __str__(self):
        return "<ValidationError errors: {}; unset: {}".format(self.errors, self.unset)

    def __repr__(self):
        return self.__str__()
