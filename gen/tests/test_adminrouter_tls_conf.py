from textwrap import dedent
from typing import List

import pytest

import gen
from gen.tests.utils import make_arguments, true_false_msg, validate_error


class TestAdminRouterTLSConfig:
    """
    Tests for the Admin Router TLS Config creation.
    """

    def test_default(self):
        """
        By default, the configuration specifies certain TLS settings.

        This test is a sanity check for the configuration template logic
        rather than a particularly useful feature test.
        """
        config_path = '/etc/adminrouter-tls.conf'
        arguments = make_arguments(new_arguments={})
        generated = gen.generate(arguments=arguments)
        package = generated.templates['dcos-config.yaml']['package']
        [config] = [item for item in package if item['path'] == config_path]

        expected_configuration = dedent(
            """\
            # Ref: https://github.com/cloudflare/sslconfig/blob/master/conf
            # Modulo ChaCha20 cipher.
            ssl_ciphers EECDH+AES128:RSA+AES128:EECDH+AES256:RSA+AES256:EECDH+3DES:RSA+3DES:!MD5;
            ssl_prefer_server_ciphers on;
            # To manually test which TLS versions are enabled on a node, use
            # `openssl` commands.
            #
            # See comments on https://jira.mesosphere.com/browse/DCOS-13437 for more
            # details.

            ssl_protocols TLSv1.1 TLSv1.2;
            """
        )
        assert config['content'] == expected_configuration


class TestToggleTLS1:
    """
    Tests for toggling TLS 1.0.

    To manually test that this is, in fact, a working toggle for TLS 1.0, use
    `openssl` commands.

    See comments on https://jira.mesosphere.com/browse/DCOS-13437 for more
    details.
    """

    def supported_ssl_protocols(self, new_config_arguments) -> List[str]:
        """
        This finds a line which looks like the following:
            ssl protocols TLSv1, TLSv1.1;
        in the Admin Router TLS configuration.
        It then returns the listed protocols.

        Args:
            new_config_arguments: Arguments which are added to the 'standard'
                set of arguments before generating configuration files.

        Returns:
            A ``list`` of supported SSL protocols.
        """
        arguments = make_arguments(new_arguments=new_config_arguments)
        generated = gen.generate(arguments=arguments)
        package = generated.templates['dcos-config.yaml']['package']
        config_path = '/etc/adminrouter-tls.conf'
        [config] = [item for item in package if item['path'] == config_path]
        [ssl_protocols_line] = [
            line for line in config['content'].split('\n') if
            # We strip whitespace from the beginning of the line as NGINX
            # configuration lines can start with whitespace.
            line.lstrip().startswith('ssl_protocols ')
        ]
        ssl_protocols_line = ssl_protocols_line.strip(';')
        protocols = ssl_protocols_line.split()[1:]
        return protocols

    def test_validation(self):
        """
        The config variable `tls_1_0_enabled` must be 'true' or 'false'.
        """
        validate_error(
            new_arguments={'adminrouter_tls_1_0_enabled': 'foo'},
            key='adminrouter_tls_1_0_enabled',
            message=true_false_msg,
        )

    @pytest.mark.parametrize(
        'new_arguments', [{}, {'adminrouter_tls_1_0_enabled': 'false'}]
    )
    def test_default(self, new_arguments):
        """
        By default TLS 1.0 is disabled, and therefore by default the config
        variable is set to 'false'.

        This test is parametrized to demonstrate that having no configuration
        produces the same results as setting the config variable to `'false'`.
        """
        protocols = self.supported_ssl_protocols(
            new_config_arguments=new_arguments,
        )
        assert protocols == ['TLSv1.1', 'TLSv1.2']

    def test_enable(self):
        """
        Setting the config variable to 'true' enables TLS 1.0.
        """
        new_arguments = {'adminrouter_tls_1_0_enabled': 'true'}
        protocols = self.supported_ssl_protocols(
            new_config_arguments=new_arguments,
        )
        assert protocols == ['TLSv1', 'TLSv1.1', 'TLSv1.2']
