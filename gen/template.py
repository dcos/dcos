#!/usr/bin/env python3
#
# Simple python templating system. Works on yaml files which are also jinja-style templates.
# Scans the jinja for the structure, and outputs an AST of the possible option combinations.
# That graph could be fed into something like an argument prompter to get
# out all the arguments.

# Simple state machine parser, hard coded. Recognizes a couple tokens:
# "template body" - arbitrary bytes
# To escape the template signature, put four `{`, so `{{{{` would result in the final result getting a `{{`.
# For closing ones, just put closing wherever. Exeess closing isn't an error, and closing is only
# consumed if opening has been passed.
# Unmatched closing }} are a hard error.
# "template variable" - {{ <identifier> }}
# "template flow conrol" - {% <control_expression %}
# The valid control expressions are:
#   switch <identifier>
#   case <string>:
#   endswith

from pkg_resources import resource_string

identifier_valid_characters = 'abcdefghijklmnopqrstuvwxyz_0123456789'


class SyntaxError(Exception):

    def __init__(self, message, filename=None):
        self.message = message
        self.filename = filename

    def __str__(self):
        if self.filename:
            return repr(self.message) + " while parsing file {}".format(self.filename)
        else:
            return repr(self.message)


class Tokenizer():

    def __init__(self, corpus):
        assert isinstance(corpus, str)
        self.__corpus = corpus
        self.__to_lex = corpus

        self.__token_pos = 0
        self.tokens = []

        while True:
            try:
                kind, value = self.__read_token()
            except SyntaxError as ex:
                # TOOD(cmaloney): Calculate line and column information
                context = "context: '{}'".format(self.__to_lex[:10])
                raise SyntaxError(
                    "ERROR parsing code near {}. {}".format(context, ex)) from ex
            self.tokens.append((kind, value))
            if kind == "eof":
                break

    def Peek(self):
        if self.__token_pos == len(self.tokens):
            raise RuntimeError("Walked past end of token list")
        return self.tokens[self.__token_pos]

    def Advance(self):
        if self.__token_pos >= len(self.tokens):
            raise RuntimeError("Walked past end of token list")
        self.__token_pos += 1
        return self.tokens[self.__token_pos]

    def __read_token(self):
        # __to_lex is set to none after the EOF token is emitted.
        assert self.__to_lex is not None

        if len(self.__to_lex) == 0:
            self.__to_lex = None
            return "eof", None

        # If not starting with '{', consume text until we find '{' as a blob
        # token.
        if self.__to_lex[0] != '{':
            split = self.__to_lex.split('{', 1)
            assert(len(split) == 1 or len(split) == 2)

            if len(split) == 2:
                self.__to_lex = '{' + split[1]
            else:
                # No remaining '{' in text. This is the end of the string.
                self.__to_lex = ''
            return 'blob', split[0]

        # Process '{' beginning control sequences.

        # Define some helper functions used by multiple methods below.
        def read_whitespace():
            if self.__to_lex[0] != ' ':
                raise SyntaxError("Expected exactly one space")
            if self.__to_lex[1].isspace():
                raise SyntaxError(
                    "Found more spaces than expected. Only one space is allowed by coding convention.")
            self.__to_lex = self.__to_lex[1:]

        def read_identifier():
            # Before identifiers is always whitespace / we're in control where
            # whitespace is arbitrary.
            read_whitespace()
            identifier = ""
            while self.__to_lex[0] in identifier_valid_characters:
                identifier += self.__to_lex[0]
                self.__to_lex = self.__to_lex[1:]
            return identifier

        def read_str():
            read_whitespace()
            if not self.__to_lex.startswith('"'):
                raise SyntaxError(
                    "Expected string starting with '\"' as value for case but didn't find it.")
            self.__to_lex = self.__to_lex[1:]

            value = ""
            has_backslash = False
            while True:
                if len(self.__to_lex) == 0:
                    raise SyntaxError(
                        "Unexpected end of file when reading contents of string")

                cur = self.__to_lex[0]
                self.__to_lex = self.__to_lex[1:]

                if cur in ['\n', '\r']:
                    raise SyntaxError("Newlines aren't allowed in strings")

                if has_backslash:
                    if cur in ['"', '\\']:
                        value += cur
                    else:
                        raise SyntaxError("Invalid escape sequence \\{} in quote".format(cur))
                    has_backslash = False
                    continue

                if cur == '\\':
                    has_backslash = True
                elif cur == '"':
                    return value
                else:
                    value += cur

        def read_end_control_group():
            # Arbitrary whitespace is allowed before end of the control group
            read_whitespace()
            if not self.__to_lex.startswith('%}'):
                raise SyntaxError(
                    "Expected end of control group '%}' after control statement but didn't find it.")
            self.__to_lex = self.__to_lex[2:]

        # Note: We want the longest match to win. Since we are doing prefix
        # matching that means we must test the longest strings which have
        # prefixes which are also valid tokens first.
        if self.__to_lex.startswith('{{{{'):
            self.__to_lex = self.__to_lex[4:]
            return "blob", "{{"
        if self.__to_lex.startswith('{{{'):
            raise SyntaxError(
                "{{{ is illegal. To make an argument substitution use " +
                "{{ <identifier> }}. To make '{{' use '{{{{'. To make '{{{' " +
                "use '{{{{{' (the first for become two, then the last is left" +
                " alone since it is all alone)")
        elif self.__to_lex.startswith('{%'):
            # TODO(cmaloney): There is fairly specific parsing happening in control and ident rather
            # than doing what they probably _should_ be doing for generic parsing. There is some
            # duplicated code. That should be removed / refactored at some point.
            # switch <identifier>
            # case <string>
            # endswitch
            self.__to_lex = self.__to_lex[2:]

            # Clean leading whitespace
            read_whitespace()

            if self.__to_lex.startswith("switch"):
                self.__to_lex = self.__to_lex[6:]
                identifier = read_identifier()
                read_end_control_group()
                return "switch", identifier
            elif self.__to_lex.startswith("case"):
                self.__to_lex = self.__to_lex[4:]
                value = read_str()
                read_end_control_group()
                return "case", value
            elif self.__to_lex.startswith("endswitch"):
                self.__to_lex = self.__to_lex[9:]
                read_end_control_group()
                return "endswitch", None
            elif self.__to_lex.startswith("for"):
                self.__to_lex = self.__to_lex[3:]
                new_var = read_identifier()
                read_whitespace()
                if not self.__to_lex.startswith("in"):
                    raise SyntaxError("Expected {% for foo in bar %}, didn't find the ' in'.")
                self.__to_lex = self.__to_lex[2:]
                iterable = read_identifier()
                read_end_control_group()
                return "for", (new_var, iterable)
            elif self.__to_lex.startswith("endfor"):
                self.__to_lex = self.__to_lex[6:]
                read_end_control_group()
                return "endfor", None
            else:
                raise SyntaxError(
                    "Unknown control group directive. Expected switch, case, or endswitch.")
        elif self.__to_lex.startswith("{{"):
            # whitespace ident whitespace close_curly
            # Clean of leading whitespace
            self.__to_lex = self.__to_lex[2:]

            try:
                identifier = read_identifier()
            except SyntaxError as ex:
                raise SyntaxError(
                    "{} while parsing argument substitution block {{{{ <identifier> }}}}.".format(ex)) from ex

            if len(identifier) == 0:
                raise SyntaxError("Identifier must be a non-empty string")

            # trailing whitespace after identifier
            read_whitespace()

            # Optionally a filter expresion
            filter_id = None
            if self.__to_lex.startswith('|'):
                self.__to_lex = self.__to_lex[1:]
                filter_id = read_identifier()
                read_whitespace()

            # Close curly braces
            if not self.__to_lex.startswith('}}'):
                raise SyntaxError(
                    "Expected '}}' after '{{ <identifier>' but didn't find it.")

            self.__to_lex = self.__to_lex[2:]
            return "replacement", (identifier, filter_id)
        else:
            # Was just a single open curly, we're a single curly blob
            self.__to_lex = self.__to_lex[1:]
            return "blob", "{"

# Language:
# template -> chunks EOF
# chunks -> chunk*
# abstract chunk
# blob:  chunk -> blob # This is represented as just a str
# replacement: chunk -> replacement
# switch: chunk -> startswitch cases endswitch
# cases -> case* # This is represented as just a dictionary
# case -> case_tok chunks


class Switch():

    def __init__(self, identifier, cases):
        assert isinstance(identifier, str)
        self.identifier = identifier
        assert isinstance(cases, dict)
        self.cases = cases

    def __repr__(self):
        return "<switch {} {}>".format(self.identifier, self.cases)

    def __eq__(self, other):
        return isinstance(other, Switch) and self.identifier == other.identifier and self.cases == other.cases


class For():
    def __init__(self, new_var, iterable, body):
        assert isinstance(new_var, str)
        self.new_var = new_var
        assert isinstance(iterable, str)
        self.iterable = iterable
        assert isinstance(body, list)
        self.body = body

    def __repr__(self):
        return "<for {} in {}>".format(self.new_var, self.iterable)

    def __eq__(self, other):
        return isinstance(other, For) and self.new_var == other.new_var and self.iterable == other.iterable


class Replacement():

    def __init__(self, identifier_and_filter):
        self.identifier = identifier_and_filter[0]
        self.filter = identifier_and_filter[1]

        assert(isinstance(self.identifier, str))
        assert(isinstance(self.filter, str) or self.filter is None)

    def __repr__(self):
        return "<replacement {}{}>".format(
            self.identifier,
            (" filter " + self.filter) if self.filter is not None else "")

    def __eq__(self, other):
        return isinstance(other, Replacement) and self.identifier == other.identifier


class UnsetParameter(KeyError):
    def __init__(self, message, identifier):
        super(KeyError, self).__init__(message)
        self.identifier = identifier


class UnsetMarker():
    pass


class Template():

    def __init__(self, ast):
        assert isinstance(ast, list)
        self.ast = ast

    def render(self, arguments, filters={}):
        assert isinstance(arguments, dict)

        def get_argument(name):
            try:
                return arguments[name]
            except KeyError:
                raise UnsetParameter("Unset parameter {}".format(name), name)

        def render_ast(ast):
            rendered = ""
            for chunk in ast:
                if isinstance(chunk, Switch):
                    choice = get_argument(chunk.identifier)
                    if choice not in chunk.cases:
                        raise ValueError("")
                    rendered += render_ast(chunk.cases[choice])
                elif isinstance(chunk, Replacement):
                    value = get_argument(chunk.identifier)
                    if chunk.filter is None:
                        rendered += str(value)
                    else:
                        try:
                            filter_func = filters[chunk.filter]
                        except KeyError:
                            raise UnsetParameter("Unset filter parameter {}".format(chunk.filter), chunk.filter)
                        rendered += str(filter_func(value))
                elif isinstance(chunk, For):
                    # If the argument is a string, it should be a json list.
                    iterable = get_argument(chunk.iterable)
                    # TODO(cmaloney): for should only be used (for now) in code which doesn't contain
                    # arbitrary user parameters.
                    # STash the original state of the argument.
                    original_value = UnsetMarker()
                    if chunk.new_var in arguments:
                        original_value = arguments[chunk.new_var]

                    assert isinstance(iterable, list)
                    for value in iterable:
                        arguments[chunk.new_var] = value
                        rendered += render_ast(chunk.body)

                    # Reset the argument to the original state.
                    if isinstance(original_value, UnsetMarker):
                        del arguments[chunk.new_var]
                    else:
                        arguments[chunk.new_var] = original_value

                elif isinstance(chunk, str):
                    rendered += chunk
                else:
                    raise NotImplementedError(
                        "Unknown chunk type {}".format(type(chunk)))

            return rendered

        return render_ast(self.ast)

    def get_scoped_arguments(self):
        def variables_from_ast(ast, blacklist):
            variables = set()
            sub_scopes = dict()
            for chunk in ast:
                if isinstance(chunk, Switch):
                    sub_scopes[chunk.identifier] = dict()
                    for value, sub_ast in chunk.cases.items():
                        sub_scopes[chunk.identifier][value] = variables_from_ast(sub_ast, blacklist)
                elif isinstance(chunk, Replacement):
                    if chunk.identifier not in blacklist:
                        variables.add(chunk.identifier)
                elif isinstance(chunk, For):
                    additions = variables_from_ast(chunk.body, blacklist | {chunk.new_var})
                    variables |= additions['variables']
                    # TODO(cmaloney): Recursively merge sub_scope dictionaries.
                    sub_scopes.update(sub_scopes)
                elif isinstance(chunk, str):
                    continue
                else:
                    raise NotImplementedError(
                        "Unknown chunk type {}".format(type(chunk)))
            return {
                'variables': variables,
                'sub_scopes': sub_scopes
            }
        return variables_from_ast(self.ast, set())

    def get_filters(self):
        def filters_from_ast(ast):
            filters = set()
            for chunk in ast:
                if isinstance(chunk, Switch):
                    for case in chunk.cases.values():
                        filters |= filters_from_ast(case)
                elif isinstance(chunk, Replacement):
                    filters.add(chunk.filter)
                elif isinstance(chunk, For):
                    filters |= filters_from_ast(chunk.body)
                elif isinstance(chunk, str):
                    continue
                else:
                    raise NotImplementedError(
                        "Unknown chunk type {}".format(type(chunk)))
            return filters

        filters = filters_from_ast(self.ast)
        filters.discard(None)
        return filters

    def __repr__(self):
        return "<template {}>".format(self.__ast)

    def __eq__(self, other):
        return isinstance(other, Template) and self.ast == other.ast


def _parse_for(tokenizer):
    token_type, value = tokenizer.Peek()
    assert token_type == 'for'

    new_var, iterable = value

    tokenizer.Advance()

    # Read out the body
    body = _parse_chunks(tokenizer)

    # Should stop reading the body at the endfor
    token_type, value = tokenizer.Peek()
    if token_type != 'endfor':
        raise ValueError("Expecting end of for, but found {}.".format(token_type))

    tokenizer.Advance()
    return For(new_var, iterable, body)


def _parse_switch(tokenizer):
    token_type, identifier = tokenizer.Peek()
    assert(token_type == 'switch')

    cases = dict()
    is_first = True

    # Immediately inside should be a case, followed by lots more of those
    tokenizer.Advance()
    while(True):
        token_type, value = tokenizer.Peek()
        if token_type == 'case':
            tokenizer.Advance()
            cases[value] = _parse_chunks(tokenizer)
        elif token_type == 'endswitch':
            tokenizer.Advance()
            return Switch(identifier, cases)
        elif token_type == 'blob':
            # Should be unreachable if not before the first as it should be picked up inside a case.
            assert is_first
            if not value.isspace():
                raise ValueError("Unexpected blob of text outside of switch case statements. Whitespace is all that is allowed.")  # noqa
            tokenizer.Advance()
        else:
            raise ValueError(
                "Unexpected token of type {} inside switch. Expected a case or endswitch.".format(token_type))
        is_first = False
    raise RuntimeError("Unexpectedly exited the while loop in _parse_switch")


def _parse_chunks(tokenizer):
    # Read Chunks
    chunks = []
    while True:
        token_type, value = tokenizer.Peek()
        if token_type == 'blob':
            chunks.append(value)
            tokenizer.Advance()
        elif token_type == 'replacement':
            chunks.append(Replacement(value))
            tokenizer.Advance()
        elif token_type == 'switch':
            chunks.append(_parse_switch(tokenizer))
        elif token_type == 'for':
            chunks.append(_parse_for(tokenizer))
        else:
            return chunks


def parse_str(text):
    tokenizer = Tokenizer(text)
    ast = _parse_chunks(tokenizer)
    token_type, _ = tokenizer.Peek()
    if token_type != "eof":
        raise ValueError(
            "Unexpected token of type {} at end of text, expecting EOF".format(token_type))
    return Template(ast)


def parse_resources(filename):
    try:
        return parse_str(resource_string(__name__, filename).decode())
    except SyntaxError as ex:
        # Don't accidentally overwrite a previously set filename. Shouldn't
        # happen since no code this calls sets ex.filename.
        assert not ex.filename
        raise SyntaxError(ex.message, filename) from ex
