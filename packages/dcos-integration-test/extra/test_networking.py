import logging

import requests
import retrying


def ensure_routable(cmd, service_points, timeout=300):
    @retrying.retry(wait_fixed=2000,
                    stop_max_delay=timeout * 1000,
                    retry_on_result=lambda ret: ret is False,
                    retry_on_exception=lambda x: True)
    def _ensure_routable():
        proxy_uri = 'http://{}:{}/run_cmd'.format(service_points[0].host, service_points[0].port)
        logging.info('Sending {} data: {}'.format(proxy_uri, cmd))
        r = requests.post(proxy_uri, data=cmd)
        logging.info('Requests Response: %s', repr(r.json()))
        assert(r.json()['status'] == 0)
    return _ensure_routable


def test_if_minuteman_routes_to_vip(cluster):
    """Test if we are able to connect to a task with a vip using minuteman.
    """
    origin_app, origin_uuid = cluster.get_test_app()
    origin_app['portDefinitions'][0]['labels'] = {'VIP_0': '1.2.3.4:5000'}

    # TODO(cmaloney): Add a "with" marathon app deployment
    cluster.deploy_marathon_app(origin_app)

    proxy_app, proxy_uuid = cluster.get_test_app()
    service_points = cluster.deploy_marathon_app(proxy_app)

    cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://1.2.3.4:5000/ping'
    ensure_routable(cmd, service_points)()

    cluster.destroy_marathon_app(origin_app['id'])
    cluster.destroy_marathon_app(proxy_app['id'])


def test_if_minuteman_routes_to_named_vip(cluster):
    """Test if we are able to connect to a task with a named vip using minuteman.
    """

    origin_app, origin_uuid = cluster.get_test_app()
    origin_app['portDefinitions'][0]['labels'] = {'VIP_0': 'foo:5000'}
    cluster.deploy_marathon_app(origin_app)

    proxy_app, proxy_uuid = cluster.get_test_app()
    service_points = cluster.deploy_marathon_app(proxy_app)

    cmd = '/opt/mesosphere/bin/curl -s -f -m 5 http://foo.marathon.l4lb.thisdcos.directory:5000/ping'
    ensure_routable(cmd, service_points)()

    cluster.destroy_marathon_app(origin_app['id'])
    cluster.destroy_marathon_app(proxy_app['id'])


def test_ip_per_container(cluster):
    """Test if we are able to connect to a task with ip-per-container mode
    """
    # Launch the test_server in ip-per-container mode

    app_definition, test_uuid = cluster.get_test_app_in_docker(ip_per_container=True)

    assert len(cluster.slaves) >= 2, "IP Per Container tests require 2 private agents to work"

    app_definition['instances'] = 2
    app_definition['constraints'] = [['hostname', 'UNIQUE']]

    service_points = cluster.deploy_marathon_app(app_definition, check_health=True)
    app_port = app_definition['container']['docker']['portMappings'][0]['containerPort']
    cmd = '/opt/mesosphere/bin/curl -s -f http://{}:{}/ping'.format(service_points[1].ip, app_port)
    ensure_routable(cmd, service_points)()
    cluster.destroy_marathon_app(app_definition['id'])
