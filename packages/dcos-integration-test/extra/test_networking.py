import logging
from subprocess import check_output

import pytest

import requests

import retrying

from pkgpanda.build import load_json
from test_util.marathon import get_test_app, get_test_app_in_docker


def lb_enabled():
    config = load_json('/opt/mesosphere/etc/expanded.config.json')
    return config['enable_lb'] == 'true'


def ensure_routable(cmd, service_points, timeout=120):
    @retrying.retry(wait_fixed=2000,
                    stop_max_delay=timeout * 1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: True)
    def _ensure_routable():
        proxy_uri = 'http://{}:{}/run_cmd'.format(service_points[0].host, service_points[0].port)
        logging.info('Sending {} data: {}'.format(proxy_uri, cmd))
        r = requests.post(proxy_uri, data=cmd)
        logging.info('Requests Response: %s', repr(r.json()))
        assert r.json()['status'] == 0
    return _ensure_routable


@retrying.retry(wait_fixed=2000,
                stop_max_delay=120 * 1000,
                retry_on_exception=lambda x: True)
def test_if_overlay_ok(cluster):
    def _check_overlay(hostname, port):
        uri = 'http://{}:{}/overlay-agent/overlay'.format(hostname, port)
        resp = requests.get(uri).json()
        overlays = resp['overlays']
        assert len(overlays) > 0
        for overlay in overlays:
            assert overlay['state']['status'] == 'STATUS_OK'

    for master in cluster.masters:
        _check_overlay(master, 5050)
    for slave in cluster.all_slaves:
        _check_overlay(slave, 5051)


@pytest.mark.skipif(lb_enabled(), reason='Load Balancer enabled')
def test_if_minuteman_disabled(cluster):
    """Test to make sure minuteman is disabled"""
    data = check_output(["/usr/bin/env", "ip", "rule"])
    # Minuteman creates this ip rule: `9999: from 9.0.0.0/8 lookup 42`
    # We check it doesn't exist
    assert str(data).find('9999') == -1


@pytest.mark.skipif(not lb_enabled(), reason='Load Balancer disabled')
def test_if_minuteman_routes_to_vip(cluster):
    """Test if we are able to connect to a task with a vip using minuteman.
    """
    origin_app, origin_uuid = get_test_app()
    origin_app['portDefinitions'][0]['labels'] = {'VIP_0': '1.2.3.4:5000'}
    with cluster.marathon.deploy_and_cleanup(origin_app):
        proxy_app, proxy_uuid = get_test_app()
        with cluster.marathon.deploy_and_cleanup(proxy_app) as service_points:
            cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://1.2.3.4:5000/ping'
            ensure_routable(cmd, service_points)()


@pytest.mark.skipif(not lb_enabled(), reason='Load Balancer disabled')
def test_if_minuteman_routes_to_named_vip(cluster):
    """Test if we are able to connect to a task with a named vip using minuteman.
    """

    origin_app, origin_uuid = get_test_app()
    origin_app['portDefinitions'][0]['labels'] = {'VIP_0': 'foo:5000'}
    with cluster.marathon.deploy_and_cleanup(origin_app):
        proxy_app, proxy_uuid = get_test_app()
        with cluster.marathon.deploy_and_cleanup(proxy_app) as service_points:
            cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://foo.marathon.l4lb.thisdcos.directory:5000/ping'
            ensure_routable(cmd, service_points)()


def test_ip_per_container(cluster):
    """Test if we are able to connect to a task with ip-per-container mode
    """
    # Launch the test_server in ip-per-container mode
    app_definition, test_uuid = get_test_app_in_docker(ip_per_container=True)

    assert len(cluster.slaves) >= 2, "IP Per Container tests require 2 private agents to work"

    app_definition['instances'] = 2
    app_definition['constraints'] = [['hostname', 'UNIQUE']]

    with cluster.marathon.deploy_and_cleanup(app_definition, check_health=True) as service_points:
        app_port = app_definition['container']['docker']['portMappings'][0]['containerPort']
        cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://{}:{}/ping'.format(service_points[1].ip, app_port)
        ensure_routable(cmd, service_points)()


@pytest.mark.skipif(not lb_enabled(), reason='Load Balancer disabled')
def test_ip_per_container_with_named_vip(cluster):
    """Test if we are able to connect to a task with ip-per-container mode using named vip
    """
    origin_app, test_uuid = get_test_app_in_docker(ip_per_container=True)
    origin_app['container']['docker']['portMappings'][0]['labels'] = {'VIP_0': 'foo:6000'}
    origin_app['healthChecks'][0]['port'] = origin_app['container']['docker']['portMappings'][0]['containerPort']
    del origin_app['container']['docker']['portMappings'][0]['hostPort']
    del origin_app['healthChecks'][0]['portIndex']

    with cluster.marathon.deploy_and_cleanup(origin_app):
        proxy_app, proxy_uuid = get_test_app()
        with cluster.marathon.deploy_and_cleanup(proxy_app) as service_points:
            cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://foo.marathon.l4lb.thisdcos.directory:6000/ping'
            ensure_routable(cmd, service_points)()
