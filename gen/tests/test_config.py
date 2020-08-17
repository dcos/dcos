import json
import tempfile

import pkg_resources
import pytest
import yaml

import gen
from gen.exceptions import ExhibitorTLSBootstrapError
from gen.tests.utils import make_arguments, true_false_msg, \
    validate_error, validate_error_multikey, validate_success


def test_invalid_telemetry_enabled():
    err_msg = "Must be one of 'true', 'false'. Got 'foo'."
    validate_error(
        {'telemetry_enabled': 'foo'},
        'telemetry_enabled',
        err_msg)


def test_invalid_enable_mesos_input_plugin():
    err_msg = "Must be one of 'true', 'false'. Got 'foo'."
    validate_error(
        {'enable_mesos_input_plugin': 'foo'},
        'enable_mesos_input_plugin',
        err_msg)


def test_resolvers():
    validate_error(
        {'resolvers': '["52.37.192.49", "52.37.181.230:53", "52.37.163.105:65536"]'},
        'resolvers',
        "Must be between 1 and 65535 inclusive")

    validate_error(
        {'resolvers': '["52.37.192.49", "52.37.181.230:53", "52.37.163.105:abc"]'},
        'resolvers',
        "Must be an integer but got a str: abc")

    validate_error(
        {'resolvers': '["52.37.192.49", "198.51.100.1:53"]'},
        'resolvers',
        'Spartan addresses found in `resolvers`: 198.51.100.1')

    validate_error(
        {'resolvers': '["198.51.100.2", "52.37.192.49:53", "198.51.100.3:53"]'},
        'resolvers',
        'Spartan addresses found in `resolvers`: 198.51.100.2, 198.51.100.3')

    validate_success(
        {'resolvers': '["8.8.8.8", "1.1.1.1:5353"]'},
    )


def test_dns_bind_ip_blacklist():
    test_ips = '["52.37.192.49", "52.37.181.230", "52.37.163.105"]'

    validate_success({'dns_bind_ip_blacklist': test_ips})


dns_forward_zones_str = """
{"a.contoso.com": ["1.1.1.1:53", "2.2.2.2"],
 "b.contoso.com": ["3.3.3.3", "4.4.4.4:53"]}
"""

bad_dns_forward_zones_str = """
{"a.contoso.com": ["1", "2.2.2.2"],
 "b.contoso.com": ["3.3.3.3", "4.4.4.4:53"]}
"""


def test_dns_forward_zones():
    zones = dns_forward_zones_str
    bad_zones = bad_dns_forward_zones_str
    err_msg = 'Invalid "dns_forward_zones": 1 not a valid IP address'

    validate_success({'dns_forward_zones': zones})

    validate_error(
        {'dns_forward_zones': bad_zones},
        'dns_forward_zones',
        err_msg)


def test_invalid_ipv4():
    test_ips = '["52.37.192.49", "52.37.181.230", "foo", "52.37.163.105", "bar"]'
    err_msg = "Invalid IPv4 addresses in list: foo, bar"

    validate_error(
        {'master_list': test_ips},
        'master_list',
        err_msg)

    validate_error(
        {'dns_bind_ip_blacklist': test_ips},
        'dns_bind_ip_blacklist',
        err_msg)

    validate_error(
        {'resolvers': test_ips},
        'resolvers',
        err_msg)


def test_invalid_zk_path():
    validate_error(
        {'exhibitor_zk_path': 'bad/path'},
        'exhibitor_zk_path',
        "Must be of the form /path/to/znode")


def test_invalid_zk_hosts():
    validate_error(
        {'exhibitor_zk_hosts': 'zk://10.10.10.10:8181'},
        'exhibitor_zk_hosts',
        "Must be of the form `host:port,host:port', not start with zk://")


def test_invalid_bootstrap_url():
    validate_error(
        {'bootstrap_url': '123abc/'},
        'bootstrap_url',
        "Must not end in a '/'")


def test_validate_duplicates():
    test_ips = '["10.0.0.1", "10.0.0.2", "10.0.0.1"]'
    err_msg = 'List cannot contain duplicates: 10.0.0.1 appears 2 times'

    validate_error(
        {'master_list': test_ips},
        'master_list',
        err_msg)

    validate_error(
        {'dns_bind_ip_blacklist': test_ips},
        'dns_bind_ip_blacklist',
        err_msg)


def test_invalid_oauth_enabled():
    validate_error(
        {'oauth_enabled': 'foo'},
        'oauth_enabled',
        true_false_msg)


def test_invalid_mesos_dns_set_truncate_bit():
    validate_error(
        {'mesos_dns_set_truncate_bit': 'foo'},
        'mesos_dns_set_truncate_bit',
        true_false_msg)


def test_validate_mesos_recovery_timeout():
    validate_success(
        {'mesos_recovery_timeout': '24hrs'})

    validate_success(
        {'mesos_recovery_timeout': '24.5hrs'})

    validate_error(
        {'mesos_recovery_timeout': '2.4.5hrs'},
        'mesos_recovery_timeout',
        "Invalid decimal format.")

    validate_error(
        {'mesos_recovery_timeout': 'asdf'},
        'mesos_recovery_timeout',
        "Error parsing 'mesos_recovery_timeout' value: asdf.")

    validate_error(
        {'mesos_recovery_timeout': '9999999999999999999999999999999999999999999ns'},
        'mesos_recovery_timeout',
        "Value 9999999999999999999999999999999999999999999 not in supported range.")

    validate_error(
        {'mesos_recovery_timeout': '1hour'},
        'mesos_recovery_timeout',
        "Unit 'hour' not in ['ns', 'us', 'ms', 'secs', 'mins', 'hrs', 'days', 'weeks'].")


def test_cluster_docker_credentials():
    validate_error(
        {'cluster_docker_credentials': 'foo'},
        'cluster_docker_credentials',
        "Must be valid JSON. Got: foo")

    validate_error(
        {'cluster_docker_credentials_dcos_owned': 'foo'},
        'cluster_docker_credentials_dcos_owned',
        true_false_msg)


def test_exhibitor_storage_master_discovery():
    msg_master_discovery = "When master_discovery is not static, exhibitor_storage_backend must be " \
        "non-static. Having a variable list of master which are discovered by agents using the " \
        "master_discovery method but also having a fixed known at install time static list of " \
        "master ips doesn't `master_http_load_balancer` then exhibitor_storage_backend must not " \
        "be static."

    validate_success({
        'exhibitor_storage_backend': 'static',
        'master_discovery': 'static'})
    validate_success({
        'exhibitor_storage_backend': 'aws_s3',
        'master_discovery': 'master_http_loadbalancer',
        'aws_region': 'foo',
        'exhibitor_address': 'http://foobar',
        'exhibitor_explicit_keys': 'false',
        'num_masters': '5',
        's3_bucket': 'baz',
        's3_prefix': 'mofo'})
    validate_success({
        'exhibitor_storage_backend': 'aws_s3',
        'master_discovery': 'static',
        'exhibitor_explicit_keys': 'false',
        's3_bucket': 'foo',
        'aws_region': 'bar',
        's3_prefix': 'baz/bar'})
    validate_error_multikey(
        {'exhibitor_storage_backend': 'static',
         'master_discovery': 'master_http_loadbalancer'},
        ['exhibitor_storage_backend', 'master_discovery'],
        msg_master_discovery,
        unset={'exhibitor_address', 'num_masters'})


def test_exhibitor_tls_enabled():
    validate_success({'exhibitor_tls_enabled': 'false'})
    validate_success({'exhibitor_tls_enabled': 'true'})
    validate_error(
        {'exhibitor_tls_enabled': 'foo'},
        'exhibitor_tls_enabled',
        true_false_msg)


def test_exhibitor_tls_required():
    validate_success({'exhibitor_tls_required': 'false'})
    validate_success({'exhibitor_tls_required': 'true'})
    validate_error(
        {'exhibitor_tls_required': 'foo'},
        'exhibitor_tls_required',
        true_false_msg)


def test_exhibitor_tls_initialize_fail():
    with pytest.raises(ExhibitorTLSBootstrapError) as exc:
        gen.generate(arguments=make_arguments({
            'platform': 'onprem',
            'exhibitor_tls_enabled': 'false',
            'exhibitor_tls_required': 'true',
        }))
    print(exc.value.errors)
    assert exc.value.errors == [
        'Exhibitor security is disabled',
        'Exhibitor security is an enterprise feature',
        'CA init in gen is only supported when using a remote bootstrap node',
    ]

    with pytest.raises(ExhibitorTLSBootstrapError) as exc:
        gen.generate(arguments=make_arguments({
            'platform': 'onprem',
            'exhibitor_tls_enabled': 'true',
            'exhibitor_tls_required': 'true',
        }))
    assert exc.value.errors == [
        'Exhibitor security is an enterprise feature',
        'CA init in gen is only supported when using a remote bootstrap node',
    ]

    with pytest.raises(ExhibitorTLSBootstrapError) as exc:
        gen.generate(arguments=make_arguments({
            'platform': 'onprem',
            'exhibitor_tls_enabled': 'true',
            'exhibitor_tls_required': 'true',
            'master_discovery': 'master_http_loadbalancer',
            'exhibitor_address': 'http://foobar',
            'num_masters': '5',
        }))
    assert exc.value.errors == [
        'Only static master discovery is supported',
        'Exhibitor security is an enterprise feature',
        'CA init in gen is only supported when using a remote bootstrap node',
    ]


def test_exhibitor_tls_initialize_prints_errors(capsys):
    gen.generate(arguments=make_arguments({
        'platform': 'onprem',
        'exhibitor_tls_enabled': 'true',
    }))
    expected_message = (
        '[gen.exhibitor_tls_bootstrap] not bootstrapping '
        'exhibitor CA: Exhibitor security is an enterprise feature'
    )
    assert expected_message in capsys.readouterr().out


def test_exhibitor_bootstrap_ca_url():
    validate_success({'exhibitor_bootstrap_ca_url': ''})
    validate_success({'exhibitor_bootstrap_ca_url': 'https://hello.com'})
    validate_success({'exhibitor_bootstrap_ca_url': 'https://1.2.3.4'})
    validate_success({'exhibitor_bootstrap_ca_url': 'https://hello.com:443'})
    validate_success({'exhibitor_bootstrap_ca_url': 'https://1.2.3.4:443'})
    validate_error(
        {'exhibitor_bootstrap_ca_url': 'https://hello.com/'},
        'exhibitor_bootstrap_ca_url',
        "Must not end in a '/'")
    validate_error(
        {'exhibitor_bootstrap_ca_url': 'https://hello.com://there'},
        'exhibitor_bootstrap_ca_url',
        'Failed to determine `exhibitor_bootstrap_ca_url` protocol.')
    validate_error(
        {'exhibitor_bootstrap_ca_url': 'http://hello.com'},
        'exhibitor_bootstrap_ca_url',
        'Expected `https://` as `exhibitor_bootstrap_ca_url` protocol.')
    validate_error(
        {'exhibitor_bootstrap_ca_url': 'file://hello.com'},
        'exhibitor_bootstrap_ca_url',
        'Expected `https://` as `exhibitor_bootstrap_ca_url` protocol.')


def test_validate_s3_prefix():
    validate_error({
        'exhibitor_storage_backend': 'aws_s3',
        'exhibitor_explicit_keys': 'false',
        'aws_region': 'bar',
        's3_bucket': 'baz',
        's3_prefix': 'baz/'},
        's3_prefix',
        'Must be a file path and cannot end in a /')
    validate_success({'s3_prefix': 'baz'})
    validate_success({'s3_prefix': 'bar/baz'})


def test_validate_default_overlay_network_name():
    msg = "Default overlay network name does not reference a defined overlay network: foo"
    validate_error_multikey(
        {'dcos_overlay_network': json.dumps({
            'vtep_subnet': '44.128.0.0/20',
            'vtep_subnet6': 'fd01:a::/64',
            'vtep_mac_oui': '70:B3:D5:00:00:00',
            'overlays': [{
                'name': 'bar',
                'subnet': '1.1.1.0/24',
                'prefix': 24
            }],
        }), 'dcos_overlay_network_default_name': 'foo'},
        ['dcos_overlay_network_default_name', 'dcos_overlay_network'],
        msg)


def test_validate_check_config():
    # No checks.
    validate_success({'check_config': json.dumps({})})
    # Valid node and cluster checks.
    validate_success({
        'check_config': json.dumps({
            'cluster_checks': {
                'cluster-check-1': {
                    'description': 'Cluster check 1',
                    'cmd': ['echo', 'cluster-check-1'],
                    'timeout': '1s',
                },
            },
            'node_checks': {
                'checks': {
                    'node-check-1': {
                        'description': 'Node check 1',
                        'cmd': ['echo', 'node-check-1'],
                        'timeout': '1s',
                    },
                    'node-check-2': {
                        'description': 'Node check 2',
                        'cmd': ['echo', 'node-check-2'],
                        'timeout': '1s',
                        'roles': ['agent']
                    },
                },
                'prestart': ['node-check-1'],
                'poststart': ['node-check-1', 'node-check-2'],
            },
        })
    })
    # Valid node checks only.
    validate_success({
        'check_config': json.dumps({
            'node_checks': {
                'checks': {
                    'node-check-1': {
                        'description': 'Node check 1',
                        'cmd': ['echo', 'node-check-1'],
                        'timeout': '1s',
                    },
                    'node-check-2': {
                        'description': 'Node check 2',
                        'cmd': ['echo', 'node-check-2'],
                        'timeout': '1s',
                        'roles': ['agent']
                    },
                },
                'prestart': ['node-check-1'],
                'poststart': ['node-check-1', 'node-check-2'],
            },
        })
    })
    # Valid cluster checks only.
    validate_success({
        'check_config': json.dumps({
            'cluster_checks': {
                'cluster-check-1': {
                    'description': 'Cluster check 1',
                    'cmd': ['echo', 'cluster-check-1'],
                    'timeout': '1s',
                },
            },
        })
    })

    # Missing check definitions.
    validate_error(
        {'check_config': json.dumps({'cluster_checks': {}})},
        'check_config',
        "Key 'cluster_checks' error: Missing key: Check name must be a nonzero length string with no whitespace",
    )
    validate_error(
        {'check_config': json.dumps({'node_checks': {}})},
        'check_config',
        "Key 'node_checks' error: Missing key: 'checks'",
    )
    validate_error(
        {
            'check_config': json.dumps({
                'node_checks': {
                    'checks': {},
                },
            })
        },
        'check_config',
        (
            "Key 'node_checks' error: Key 'checks' error: Missing key: Check name must be a nonzero length string "
            "with no whitespace"
        ),
    )

    # Invalid check names.
    validate_error(
        {
            'check_config': json.dumps({
                'cluster_checks': {
                    'cluster check 1': {
                        'description': 'Cluster check 1',
                        'cmd': ['echo', 'cluster-check-1'],
                        'timeout': '1s',
                    },
                },
            })
        },
        'check_config',
        "Key 'cluster_checks' error: Missing key: Check name must be a nonzero length string with no whitespace",
    )
    validate_error(
        {
            'check_config': json.dumps({
                'node_checks': {
                    'checks': {
                        'node check 1': {
                            'description': 'Node check 1',
                            'cmd': ['echo', 'node-check-1'],
                            'timeout': '1s',
                        },
                    },
                    'prestart': ['node-check-1'],
                },
            })
        },
        'check_config',
        (
            "Key 'node_checks' error: Key 'checks' error: Missing key: Check name must be a nonzero length string "
            "with no whitespace"
        ),
    )
    validate_error(
        {
            'check_config': json.dumps({
                'node_checks': {
                    'checks': {
                        'node-check-1': {
                            'description': 'Node check 1',
                            'cmd': ['echo', 'node-check-1'],
                            'timeout': '1s',
                        },
                    },
                    'prestart': ['node check 1'],
                },
            })
        },
        'check_config',
        'Check name must be a nonzero length string with no whitespace',
    )
    validate_error(
        {
            'check_config': json.dumps({
                'node_checks': {
                    'checks': {
                        'node-check-1': {
                            'description': 'Node check 1',
                            'cmd': ['echo', 'node-check-1'],
                            'timeout': '1s',
                        },
                    },
                    'poststart': ['node check 1'],
                },
            })
        },
        'check_config',
        'Check name must be a nonzero length string with no whitespace',
    )

    # Invalid timeouts.
    validate_error(
        {
            'check_config': json.dumps({
                'cluster_checks': {
                    'cluster-check-1': {
                        'description': 'Cluster check 1',
                        'cmd': ['echo', 'cluster-check-1'],
                        'timeout': '1second',
                    },
                },
            })
        },
        'check_config',
        'Timeout must be a string containing an integer or float followed by a unit: ns, us, µs, ms, s, m, h',
    )
    validate_error(
        {
            'check_config': json.dumps({
                'node_checks': {
                    'checks': {
                        'node-check-1': {
                            'description': 'Node check 1',
                            'cmd': ['echo', 'node-check-1'],
                            'timeout': '1 s',
                        },
                    },
                    'poststart': ['node-check-1'],
                },
            })
        },
        'check_config',
        'Timeout must be a string containing an integer or float followed by a unit: ns, us, µs, ms, s, m, h',
    )

    # Missing check description.
    validate_error(
        {
            'check_config': json.dumps({
                'cluster_checks': {
                    'cluster-check-1': {
                        'cmd': ['echo', 'cluster-check-1'],
                        'timeout': '1s',
                    },
                },
            })
        },
        'check_config',
        "Key 'cluster_checks' error: Key 'cluster-check-1' error: Missing key: 'description'",
    )
    validate_error(
        {
            'check_config': json.dumps({
                'node_checks': {
                    'checks': {
                        'node-check-1': {
                            'cmd': ['echo', 'node-check-1'],
                            'timeout': '1s',
                        },
                    },
                    'poststart': ['node-check-1'],
                },
            })
        },
        'check_config',
        "Key 'node_checks' error: Key 'checks' error: Key 'node-check-1' error: Missing key: 'description'",
    )

    # Check cmd is wrong type.
    validate_error(
        {
            'check_config': json.dumps({
                'cluster_checks': {
                    'cluster-check-1': {
                        'description': 'Cluster check 1',
                        'cmd': 'echo cluster-check-1',
                        'timeout': '1s',
                    },
                },
            })
        },
        'check_config',
        (
            "Key 'cluster_checks' error: Key 'cluster-check-1' error: Key 'cmd' error: 'echo cluster-check-1' should "
            "be instance of 'list'"
        ),
    )
    validate_error(
        {
            'check_config': json.dumps({
                'node_checks': {
                    'checks': {
                        'node-check-1': {
                            'cmd': 'echo node-check-1',
                            'timeout': '1s',
                        },
                    },
                    'poststart': ['node-check-1'],
                },
            })
        },
        'check_config',
        (
            "Key 'node_checks' error: Key 'checks' error: Key 'node-check-1' error: Key 'cmd' error: "
            "'echo node-check-1' should be instance of 'list'"
        ),
    )

    # Missing node prestart and poststart check lists.
    validate_error(
        {
            'check_config': json.dumps({
                'node_checks': {
                    'checks': {
                        'node-check-1': {
                            'description': 'Node check 1',
                            'cmd': ['echo', 'node-check-1'],
                            'timeout': '1s',
                        },
                    },
                },
            })
        },
        'check_config',
        'At least one of prestart or poststart must be defined in node_checks',
    )
    # Checks missing from both prestart and poststart.
    validate_error(
        {
            'check_config': json.dumps({
                'node_checks': {
                    'checks': {
                        'node-check-1': {
                            'description': 'Node check 1',
                            'cmd': ['echo', 'node-check-1'],
                            'timeout': '1s',
                        },
                        'node-check-2': {
                            'description': 'Node check 2',
                            'cmd': ['echo', 'node-check-2'],
                            'timeout': '1s',
                        },
                    },
                    'poststart': ['node-check-1'],
                },
            })
        },
        'check_config',
        'All node checks must be referenced in either prestart or poststart, or both',
    )
    # Checks referenced in prestart or poststart but not defined.
    validate_error(
        {
            'check_config': json.dumps({
                'node_checks': {
                    'checks': {
                        'node-check-1': {
                            'description': 'Node check 1',
                            'cmd': ['echo', 'node-check-1'],
                            'timeout': '1s',
                        },
                        'node-check-2': {
                            'description': 'Node check 2',
                            'cmd': ['echo', 'node-check-2'],
                            'timeout': '1s',
                        },
                    },
                    'poststart': ['node-check-1', 'node-check-2', 'node-check-3'],
                },
            })
        },
        'check_config',
        'All node checks must be referenced in either prestart or poststart, or both',
    )
    # Invalid node check role.
    validate_error(
        {
            'check_config': json.dumps({
                'node_checks': {
                    'checks': {
                        'node-check-1': {
                            'description': 'Node check 1',
                            'cmd': ['echo', 'node-check-1'],
                            'timeout': '1s',
                            'roles': ['master', 'foo'],
                        },
                    },
                    'poststart': ['node-check-1'],
                },
            })
        },
        'check_config',
        'roles must be a list containing master or agent or both',
    )


def test_validate_custom_checks():
    check_config = json.dumps({
        'cluster_checks': {
            'cluster-check-1': {
                'description': 'Cluster check 1',
                'cmd': ['echo', 'cluster-check-1'],
                'timeout': '1s',
            },
        },
        'node_checks': {
            'checks': {
                'node-check-1': {
                    'description': 'Node check 1',
                    'cmd': ['echo', 'node-check-1'],
                    'timeout': '1s',
                },
                'node-check-2': {
                    'description': 'Node check 2',
                    'cmd': ['echo', 'node-check-2'],
                    'timeout': '1s',
                    'roles': ['agent']
                },
            },
            'prestart': ['node-check-1'],
            'poststart': ['node-check-1', 'node-check-2'],
        },
    })
    custom_checks = json.dumps({
        'cluster_checks': {
            'custom-cluster-check-1': {
                'description': 'Custom cluster check 1',
                'cmd': ['echo', 'custom-cluster-check-1'],
                'timeout': '1s',
            },
        },
        'node_checks': {
            'checks': {
                'custom-node-check-1': {
                    'description': 'Custom node check 1',
                    'cmd': ['echo', 'custom-node-check-1'],
                    'timeout': '1s',
                },
            },
            'prestart': ['custom-node-check-1'],
            'poststart': ['custom-node-check-1'],
        }
    })

    # Empty and non-empty check_config and custom_checks.
    validate_success({
        'check_config': json.dumps({}),
        'custom_checks': json.dumps({}),
    })
    validate_success({
        'check_config': check_config,
        'custom_checks': json.dumps({}),
    })
    validate_success({
        'check_config': check_config,
        'custom_checks': custom_checks,
    })
    validate_success({
        'check_config': json.dumps({}),
        'custom_checks': custom_checks,
    })

    # Invalid custom checks.
    validate_error(
        {
            'custom_checks': json.dumps({
                'node_checks': {
                    'checks': {
                        'node-check-1': {
                            'description': 'Node check 1',
                            'cmd': ['echo', 'node-check-1'],
                            'timeout': '1s',
                        },
                        'node-check-2': {
                            'description': 'Node check 2',
                            'cmd': ['echo', 'node-check-2'],
                            'timeout': '1s',
                        },
                    },
                    'poststart': ['node-check-1', 'node-check-2', 'node-check-3'],
                },
            })
        },
        'custom_checks',
        'All node checks must be referenced in either prestart or poststart, or both',
    )

    # Custom checks re-use check name used by builtin checks.
    validate_error_multikey(
        {
            'check_config': check_config,
            'custom_checks': json.dumps({
                'cluster_checks': {
                    'cluster-check-1': {
                        'description': 'Cluster check 1',
                        'cmd': ['echo', 'cluster-check-1'],
                        'timeout': '1s',
                    },
                },
                'node_checks': {
                    'checks': {
                        'node-check-1': {
                            'description': 'Node check 1',
                            'cmd': ['echo', 'node-check-1'],
                            'timeout': '1s',
                        },
                        'node-check-2': {
                            'description': 'Node check 2',
                            'cmd': ['echo', 'node-check-2'],
                            'timeout': '1s',
                        },
                    },
                    'poststart': ['node-check-1', 'node-check-2'],
                },
            }),
        },
        ['check_config', 'custom_checks'],
        (
            'Custom check names conflict with builtin checks. Reserved cluster check names: cluster-check-1. Reserved '
            'node check names: node-check-1, node-check-2.'
        ),
    )


def test_validate_mesos_work_dir():
    validate_success({
        'mesos_master_work_dir': '/var/foo',
        'mesos_agent_work_dir': '/var/foo',
    })

    # Relative path.
    validate_error(
        {'mesos_master_work_dir': 'foo'},
        'mesos_master_work_dir',
        'Must be an absolute filesystem path',
    )
    validate_error(
        {'mesos_agent_work_dir': 'foo'},
        'mesos_agent_work_dir',
        'Must be an absolute filesystem path',
    )

    # Empty work dir.
    validate_error(
        {'mesos_master_work_dir': ''},
        'mesos_master_work_dir',
        'Must be an absolute filesystem path',
    )
    validate_error(
        {'mesos_agent_work_dir': ''},
        'mesos_agent_work_dir',
        'Must be an absolute filesystem path',
    )


def test_invalid_mesos_cni_root_dir_persist():
    validate_error(
        {'mesos_cni_root_dir_persist': 'foo'},
        'mesos_cni_root_dir_persist',
        true_false_msg)


def test_fault_domain_disabled():
    arguments = make_arguments(new_arguments={
        'fault_domain_detect_filename': pkg_resources.resource_filename('gen', 'fault-domain-detect/aws.sh')
    })

    generated = gen.generate(arguments=arguments)

    assert generated.arguments['fault_domain_enabled'] == 'false'
    assert 'fault_domain_detect_contents' not in generated.arguments


def test_exhibitor_admin_password_obscured():
    var_name = 'exhibitor_admin_password'
    var_value = 'secret'
    generated = gen.generate(make_arguments(new_arguments={var_name: var_value}))

    assert var_name not in json.loads(generated.arguments['expanded_config'])
    assert json.loads(generated.arguments['expanded_config_full'])[var_name] == var_value

    assert json.loads(generated.arguments['user_arguments'])[var_name] == '**HIDDEN**'
    assert json.loads(generated.arguments['user_arguments_full'])[var_name] == var_value

    assert yaml.safe_load(generated.arguments['config_yaml'])[var_name] == '**HIDDEN**'
    assert yaml.safe_load(generated.arguments['config_yaml_full'])[var_name] == var_value


def test_edited_ip_detect_script_yields_new_packages():
    with tempfile.NamedTemporaryFile() as f:
        arguments = make_arguments(new_arguments={'ip_detect_filename': f.name})

        f.write('initial script contents\n'.encode('utf-8'))
        f.flush()
        initial_cluster_packages = gen.generate(arguments).cluster_packages

        # Running genconf with the same config yields the same set of packages.
        initial_cluster_packages_rerun = gen.generate(arguments).cluster_packages
        assert initial_cluster_packages == initial_cluster_packages_rerun

        f.seek(0)
        f.truncate()
        f.write('edited script contents\n'.encode('utf-8'))
        f.flush()
        edited_cluster_packages = gen.generate(arguments).cluster_packages

        # Running genconf with an edited IP detect script yields a new set of packages.
        assert initial_cluster_packages != edited_cluster_packages


def test_validate_mesos_default_container_shm_size():
    validate_success({'mesos_default_container_shm_size': '64MB'})

    validate_success({'mesos_default_container_shm_size': '1gb'})

    validate_error_multikey(
        {'mesos_default_container_shm_size': '64.5MB'},
        ['mesos_default_container_shm_size', 'has_mesos_default_container_shm_size'],
        "Fractional bytes: 64.5.")

    validate_error_multikey(
        {'mesos_default_container_shm_size': 'asdf'},
        ['mesos_default_container_shm_size', 'has_mesos_default_container_shm_size'],
        "Error parsing 'mesos_default_container_shm_size' value: asdf.")

    validate_error_multikey(
        {'mesos_default_container_shm_size': '64PB'},
        ['mesos_default_container_shm_size', 'has_mesos_default_container_shm_size'],
        "Unit 'PB' not in ['B', 'KB', 'MB', 'GB', 'TB'].")
