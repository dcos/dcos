import gzip
import json
import logging
import os
import tempfile
import zipfile

import requests
import retrying

BASE_ENDPOINT_3DT = '/system/health/v1'
PORT_3DT = 1050
PORT_3DT_AGENT = 61001
# Expected latency for all 3dt units to refresh after postflight
LATENCY = 60


def make_3dt_request(ip, endpoint, cluster, port=80):
    """
    a helper function to get info from 3dt endpoint. Default port is 80 for pulled data from agents.
    if a destination port in 80, that means all requests should go though master (adminrouter) and we can re-use
    cluster.get otherwise we can query 3dt agents directly to port 61001 (agent-adminrouter).
    """
    if port == 80:
        assert endpoint.startswith('/'), 'endpoint {} must start with /'.format(endpoint)
        logging.info('GET {}'.format(endpoint))
        json_response = cluster.get(path=endpoint).json()
        logging.info('Response: {}'.format(json_response))
        return json_response

    url = 'http://{}:{}/{}'.format(ip, port, endpoint.lstrip('/'))
    logging.info('GET {}'.format(url))
    request = requests.get(url)
    assert request.ok
    try:
        json_response = request.json()
        logging.info('Response: {}'.format(json_response))
    except ValueError:
        logging.error('Coult not deserialized json response from {}'.format(url))
        raise
    assert len(json_response) > 0, 'json response is invalid from {}'.format(url)
    return json_response


@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY*1000)
def test_3dt_health(cluster):
    """
    test health endpoint /system/health/v1
    """
    required_fields = ['units', 'hostname', 'ip', 'dcos_version', 'node_role', 'mesos_id', '3dt_version', 'system']
    required_fields_unit = ['id', 'health', 'output', 'description', 'help', 'name']
    required_system_fields = ['memory', 'load_avarage', 'partitions', 'disk_usage']

    # Check all masters 3DT instances on base port since this is extra-cluster request (outside localhost)
    for host in cluster.masters:
        response = make_3dt_request(host, BASE_ENDPOINT_3DT, cluster, port=PORT_3DT)
        assert len(response) == len(required_fields), 'response must have the following fields: {}'.format(
            ', '.join(required_fields)
        )

        # validate units
        assert 'units' in response, 'units field not found'
        assert isinstance(response['units'], list), 'units field must be a list'
        assert len(response['units']) > 0, 'units field cannot be empty'
        for unit in response['units']:
            assert len(unit) == len(required_fields_unit), 'unit must have the following fields: {}'.format(
                ', '.join(required_fields_unit)
            )
            for required_field_unit in required_fields_unit:
                assert required_field_unit in unit, '{} must be in a unit repsonse'

            # id, health and description cannot be empty
            assert unit['id'], 'id field cannot be empty'
            assert unit['health'] in [0, 1], 'health field must be 0 or 1'
            assert unit['description'], 'description field cannot be empty'

        # check all required fields but units
        for required_field in required_fields[1:]:
            assert required_field in response, '{} field not found'.format(required_field)
            assert response[required_field], '{} cannot be empty'.format(required_field)

        # check system metrics
        assert len(response['system']) == len(required_system_fields), 'fields required: {}'.format(
            ', '.join(required_system_fields))

        for sys_field in required_system_fields:
            assert sys_field in response['system'], 'system metric {} is missing'.format(sys_field)
            assert response['system'][sys_field], 'system metric {} cannot be empty'.format(sys_field)

    # Check all agents running 3DT behind agent-adminrouter on 61001
    for host in cluster.slaves:
        response = make_3dt_request(host, BASE_ENDPOINT_3DT, cluster, port=PORT_3DT_AGENT)
        assert len(response) == len(required_fields), 'response must have the following fields: {}'.format(
            ', '.join(required_fields)
        )

        # validate units
        assert 'units' in response, 'units field not found'
        assert isinstance(response['units'], list), 'units field must be a list'
        assert len(response['units']) > 0, 'units field cannot be empty'
        for unit in response['units']:
            assert len(unit) == len(required_fields_unit), 'unit must have the following fields: {}'.format(
                ', '.join(required_fields_unit)
            )
            for required_field_unit in required_fields_unit:
                assert required_field_unit in unit, '{} must be in a unit repsonse'

            # id, health and description cannot be empty
            assert unit['id'], 'id field cannot be empty'
            assert unit['health'] in [0, 1], 'health field must be 0 or 1'
            assert unit['description'], 'description field cannot be empty'

        # check all required fields but units
        for required_field in required_fields[1:]:
            assert required_field in response, '{} field not found'.format(required_field)
            assert response[required_field], '{} cannot be empty'.format(required_field)

        # check system metrics
        assert len(response['system']) == len(required_system_fields), 'fields required: {}'.format(
            ', '.join(required_system_fields))

        for sys_field in required_system_fields:
            assert sys_field in response['system'], 'system metric {} is missing'.format(sys_field)
            assert response['system'][sys_field], 'system metric {} cannot be empty'.format(sys_field)


def validate_node(nodes):
    assert isinstance(nodes, list), 'input argument must be a list'
    assert len(nodes) > 0, 'input argument cannot be empty'
    required_fields = ['host_ip', 'health', 'role']

    for node in nodes:
        logging.info('check node reponse: {}'.format(node))
        assert len(node) == len(required_fields), 'node should have the following fields: {}'.format(
            ', '.join(required_fields)
        )
        for required_field in required_fields:
            assert required_field in node, '{} must be in node'.format(required_field)

        # host_ip, health, role fields cannot be empty
        assert node['health'] in [0, 1], 'health must be 0 or 1'
        assert node['host_ip'], 'host_ip cannot be empty'
        assert node['role'], 'role cannot be empty'


@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY*1000)
def test_3dt_nodes(cluster):
    """
    test a list of nodes with statuses endpoint /system/health/v1/nodes
    """
    for master in cluster.masters:
        response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes', cluster)
        assert len(response) == 1, 'nodes response must have only one field: nodes'
        assert 'nodes' in response
        assert isinstance(response['nodes'], list)
        assert len(response['nodes']) == len(cluster.masters + cluster.all_slaves), (
            'a number of nodes in response must be {}'.format(len(cluster.masters + cluster.all_slaves)))

        # test nodes
        validate_node(response['nodes'])


def test_3dt_nodes_node(cluster):
    """
    test a specific node enpoint /system/health/v1/nodes/<node>
    """
    for master in cluster.masters:
        # get a list of nodes
        response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes', cluster)
        nodes = list(map(lambda node: node['host_ip'], response['nodes']))
        logging.info('received the following nodes: {}'.format(nodes))

        for node in nodes:
            node_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes/{}'.format(node), cluster)
            validate_node([node_response])


def validate_units(units):
    assert isinstance(units, list), 'input argument must be list'
    assert len(units) > 0, 'input argument cannot be empty'
    required_fields = ['id', 'name', 'health', 'description']

    for unit in units:
        logging.info('validating unit {}'.format(unit))
        assert len(unit) == len(required_fields), 'a unit must have the following fields: {}'.format(
            ', '.join(required_fields)
        )
        for required_field in required_fields:
            assert required_field in unit, 'unit response must have field: {}'.format(required_field)

        # a unit must have all 3 fields not empty
        assert unit['id'], 'id field cannot be empty'
        assert unit['name'], 'name field cannot be empty'
        assert unit['health'] in [0, 1], 'health must be 0 or 1'
        assert unit['description'], 'description field cannot be empty'


def validate_unit(unit):
    assert isinstance(unit, dict), 'input argument must be a dict'
    logging.info('validating unit: {}'.format(unit))

    required_fields = ['id', 'health', 'output', 'description', 'help', 'name']
    assert len(unit) == len(required_fields), 'unit must have the following fields: {}'.format(
        ', '.join(required_fields)
    )
    for required_field in required_fields:
        assert required_field in unit, '{} must be in a unit'.format(required_field)

    # id, name, health, description, help should not be empty
    assert unit['id'], 'id field cannot be empty'
    assert unit['name'], 'name field cannot be empty'
    assert unit['health'] in [0, 1], 'health must be 0 or 1'
    assert unit['description'], 'description field cannot be empty'
    assert unit['help'], 'help field cannot be empty'


def test_3dt_nodes_node_units(cluster):
    """
    test a list of units from a specific node, endpoint /system/health/v1/nodes/<node>/units
    """
    for master in cluster.masters:
        # get a list of nodes
        response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes', cluster)
        nodes = list(map(lambda node: node['host_ip'], response['nodes']))
        logging.info('received the following nodes: {}'.format(nodes))

        for node in nodes:
            node_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes/{}'.format(node), cluster)
            logging.info('node reponse: {}'.format(node_response))
            units_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes/{}/units'.format(node), cluster)
            logging.info('units reponse: {}'.format(units_response))

            assert len(units_response) == 1, 'unit response should have only 1 field `units`'
            assert 'units' in units_response
            validate_units(units_response['units'])


def test_3dt_nodes_node_units_unit(cluster):
    """
    test a specific unit for a specific node, endpoint /system/health/v1/nodes/<node>/units/<unit>
    """
    for master in cluster.masters:
        response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes', cluster)
        nodes = list(map(lambda node: node['host_ip'], response['nodes']))
        for node in nodes:
            units_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes/{}/units'.format(node), cluster)
            unit_ids = list(map(lambda unit: unit['id'], units_response['units']))
            logging.info('unit ids: {}'.format(unit_ids))

            for unit_id in unit_ids:
                validate_unit(
                    make_3dt_request(master, BASE_ENDPOINT_3DT + '/nodes/{}/units/{}'.format(node, unit_id), cluster))


@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY*1000)
def test_3dt_units(cluster):
    """
    test a list of collected units, endpoint /system/health/v1/units
    """
    # get all unique unit names
    all_units = set()
    for node in cluster.masters:
        node_response = make_3dt_request(node, BASE_ENDPOINT_3DT, cluster, port=PORT_3DT)
        for unit in node_response['units']:
            all_units.add(unit['id'])

    for node in cluster.all_slaves:
        node_response = make_3dt_request(node, BASE_ENDPOINT_3DT, cluster, port=PORT_3DT_AGENT)
        for unit in node_response['units']:
            all_units.add(unit['id'])

    logging.info('Master units: {}'.format(all_units))

    # test agaist masters
    for master in cluster.masters:
        units_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units', cluster)
        validate_units(units_response['units'])

        pulled_units = list(map(lambda unit: unit['id'], units_response['units']))
        logging.info('collected units: {}'.format(pulled_units))
        assert set(pulled_units) == all_units, 'not all units have been collected by 3dt puller, missing: {}'.format(
            set(pulled_units).symmetric_difference(all_units)
        )


def test_3dt_units_unit(cluster):
    """
    test a unit response in a right format, endpoint: /system/health/v1/units/<unit>
    """
    for master in cluster.masters:
        units_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units', cluster)
        pulled_units = list(map(lambda unit: unit['id'], units_response['units']))
        for unit in pulled_units:
            unit_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units/{}'.format(unit), cluster)
            validate_units([unit_response])


def make_nodes_ip_map(cluster):
    """
    a helper function to make a map detected_ip -> external_ip
    """
    node_private_public_ip_map = {}
    for node in cluster.masters:
        detected_ip = make_3dt_request(node, BASE_ENDPOINT_3DT, cluster, port=PORT_3DT)['ip']
        node_private_public_ip_map[detected_ip] = node

    for node in cluster.slaves:
        detected_ip = make_3dt_request(node, BASE_ENDPOINT_3DT, cluster, port=PORT_3DT_AGENT)['ip']
        node_private_public_ip_map[detected_ip] = node

    logging.info('detected ips: {}'.format(node_private_public_ip_map))
    return node_private_public_ip_map


@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY*1000)
def test_3dt_units_unit_nodes(cluster):
    """
    test a list of nodes for a specific unit, endpoint /system/health/v1/units/<unit>/nodes
    """
    nodes_ip_map = make_nodes_ip_map(cluster)

    for master in cluster.masters:
        units_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units', cluster)
        pulled_units = list(map(lambda unit: unit['id'], units_response['units']))
        for unit in pulled_units:
            nodes_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units/{}/nodes'.format(unit), cluster)
            validate_node(nodes_response['nodes'])

        # make sure dcos-mesos-master.service has master nodes and dcos-mesos-slave.service has agent nodes
        master_nodes_response = make_3dt_request(
            master, BASE_ENDPOINT_3DT + '/units/dcos-mesos-master.service/nodes', cluster)
        master_nodes = list(map(lambda node: nodes_ip_map.get(node['host_ip']), master_nodes_response['nodes']))
        logging.info('master_nodes: {}'.format(master_nodes))

        assert len(master_nodes) == len(cluster.masters), '{} != {}'.format(master_nodes, cluster.masters)
        assert set(master_nodes) == set(cluster.masters), 'a list of difference: {}'.format(
            set(master_nodes).symmetric_difference(set(cluster.masters))
        )

        agent_nodes_response = make_3dt_request(
            master, BASE_ENDPOINT_3DT + '/units/dcos-mesos-slave.service/nodes', cluster)
        agent_nodes = list(map(lambda node: nodes_ip_map.get(node['host_ip']), agent_nodes_response['nodes']))
        logging.info('aget_nodes: {}'.format(agent_nodes))
        assert len(agent_nodes) == len(cluster.slaves), '{} != {}'.format(agent_nodes, cluster.slaves)


def test_3dt_units_unit_nodes_node(cluster):
    """
    test a specific node for a specific unit, endpoint /system/health/v1/units/<unit>/nodes/<node>
    """
    required_node_fields = ['host_ip', 'health', 'role', 'output', 'help']

    for master in cluster.masters:
        units_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units', cluster)
        pulled_units = list(map(lambda unit: unit['id'], units_response['units']))
        logging.info('pulled units: {}'.format(pulled_units))
        for unit in pulled_units:
            nodes_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/units/{}/nodes'.format(unit), cluster)
            pulled_nodes = list(map(lambda node: node['host_ip'], nodes_response['nodes']))
            logging.info('pulled nodes: {}'.format(pulled_nodes))
            for node in pulled_nodes:
                node_response = make_3dt_request(
                    master, BASE_ENDPOINT_3DT + '/units/{}/nodes/{}'.format(unit, node), cluster)
                logging.info('node response: {}'.format(node_response))
                assert len(node_response) == len(required_node_fields), 'required fields: {}'.format(
                    ', '.format(required_node_fields)
                )

                for required_node_field in required_node_fields:
                    assert required_node_field in node_response, 'field {} must be set'.format(required_node_field)

                # host_ip, health, role, help cannot be empty
                assert node_response['host_ip'], 'host_ip field cannot be empty'
                assert node_response['health'] in [0, 1], 'health must be 0 or 1'
                assert node_response['role'], 'role field cannot be empty'
                assert node_response['help'], 'help field cannot be empty'


def test_3dt_report(cluster):
    """
    test 3dt report endpoint /system/health/v1/report
    """
    for master in cluster.masters:
        report_response = make_3dt_request(master, BASE_ENDPOINT_3DT + '/report', cluster)
        assert 'Units' in report_response
        assert len(report_response['Units']) > 0

        assert 'Nodes' in report_response
        assert len(report_response['Nodes']) > 0


def _get_bundle_list(cluster):
    list_url = '/system/health/v1/report/diagnostics/list/all'
    response = cluster.get(path=list_url).json()
    logging.info('GET {}, response: {}'.format(list_url, response))

    bundles = []
    for _, bundle_list in response.items():
        if bundle_list is not None and isinstance(bundle_list, list) and len(bundle_list) > 0:
            # append bundles and get just the filename.
            bundles += map(lambda s: os.path.basename(s['file_name']), bundle_list)
    return bundles


def test_3dt_bundle_create(cluster):
    """
    test bundle create functionality
    """

    # start the diagnostics bundle job
    create_url = '/system/health/v1/report/diagnostics/create'
    response = cluster.post(path=create_url, payload={"nodes": ["all"]}).json()
    logging.info('POST {}, response: {}'.format(create_url, response))

    # make sure the job is done, timeout is 5 sec, wait between retying is 1 sec
    status_url = '/system/health/v1/report/diagnostics/status/all'

    @retrying.retry(stop_max_delay=8000, wait_fixed=1000)
    def wait_for_job():
        response = cluster.get(path=status_url).json()
        logging.info('GET {}, response: {}'.format(status_url, response))

        # check `is_running` attribute for each host. All of them must be False
        for _, attributes in response.items():
            assert not attributes['is_running']

        # sometimes it may take extra seconds to list bundles after the job is finished.
        # the job should finish within 5 seconds and listing should be available after 3 seconds.
        assert _get_bundle_list(cluster), 'get a list of bundles timeout'

    wait_for_job()

    # the job should be complete at this point.
    # check the listing for a zip file
    bundles = _get_bundle_list(cluster)
    assert len(bundles) == 1, 'bundle file not found'
    assert bundles[0] == response['extra']['bundle_name']


def verify_unit_response(zip_ext_file):
    assert isinstance(zip_ext_file, zipfile.ZipExtFile)
    unit_output = gzip.decompress(zip_ext_file.read())

    # TODO: This seems like a really fragile string to be searching for. This might need to be changed for
    # different localizations.
    assert 'Hint: You are currently not seeing messages from other users and the system' not in str(unit_output), (
        '3dt does not have permission to run `journalctl`')


@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY*1000)
def test_3dt_bundle_download_and_extract(cluster):
    """
    test bundle download and validate zip file
    """

    bundles = _get_bundle_list(cluster)
    assert bundles

    expected_common_files = ['dmesg-0.output.gz', 'opt/mesosphere/active.buildinfo.full.json.gz', '3dt-health.json']

    # these files are expected to be in archive for a master host
    expected_master_files = ['dcos-mesos-master.service.gz'] + expected_common_files

    # for agent host
    expected_agent_files = ['dcos-mesos-slave.service.gz'] + expected_common_files

    # for public agent host
    expected_public_agent_files = ['dcos-mesos-slave-public.service.gz'] + expected_common_files

    with tempfile.TemporaryDirectory() as tmp_dir:
        download_base_url = '/system/health/v1/report/diagnostics/serve'
        for bundle in bundles:
            bundle_full_location = os.path.join(tmp_dir, bundle)
            with open(bundle_full_location, 'wb') as f:
                r = cluster.get(path=os.path.join(download_base_url, bundle), stream=True)
                for chunk in r.iter_content(1024):
                    f.write(chunk)

            # validate bundle zip file.
            assert zipfile.is_zipfile(bundle_full_location)
            z = zipfile.ZipFile(bundle_full_location)

            # get a list of all files in a zip archive.
            archived_items = z.namelist()

            # make sure all required log files for master node are in place.
            for master_ip in cluster.masters:
                master_folder = master_ip + '_master/'

                # try to load 3dt health report and validate the report is for this host
                health_report = json.loads(z.read(master_folder + '3dt-health.json').decode())
                assert 'ip' in health_report
                assert health_report['ip'] == master_ip

                # make sure systemd unit output is correct and does not contain error message
                gzipped_unit_output = z.open(master_folder + 'dcos-mesos-master.service.gz')
                verify_unit_response(gzipped_unit_output)

                for expected_master_file in expected_master_files:
                    expected_file = master_folder + expected_master_file
                    assert expected_file in archived_items, 'expecting {} in {}'.format(expected_file, archived_items)

            # make sure all required log files for agent node are in place.
            for slave_ip in cluster.slaves:
                agent_folder = slave_ip + '_agent/'

                # try to load 3dt health report and validate the report is for this host
                health_report = json.loads(z.read(agent_folder + '3dt-health.json').decode())
                assert 'ip' in health_report
                assert health_report['ip'] == slave_ip

                # make sure systemd unit output is correct and does not contain error message
                gzipped_unit_output = z.open(agent_folder + 'dcos-mesos-slave.service.gz')
                verify_unit_response(gzipped_unit_output)

                for expected_agent_file in expected_agent_files:
                    expected_file = agent_folder + expected_agent_file
                    assert expected_file in archived_items, 'expecting {} in {}'.format(expected_file, archived_items)

            # make sure all required log files for public agent node are in place.
            for public_slave_ip in cluster.public_slaves:
                agent_public_folder = public_slave_ip + '_agent_public/'

                # try to load 3dt health report and validate the report is for this host
                health_report = json.loads(z.read(agent_public_folder + '3dt-health.json').decode())
                assert 'ip' in health_report
                assert health_report['ip'] == public_slave_ip

                # make sure systemd unit output is correct and does not contain error message
                gzipped_unit_output = z.open(agent_public_folder + 'dcos-mesos-slave-public.service.gz')
                verify_unit_response(gzipped_unit_output)

                for expected_public_agent_file in expected_public_agent_files:
                    expected_file = agent_public_folder + expected_public_agent_file
                    assert expected_file in archived_items, ('expecting {} in {}'.format(expected_file, archived_items))


def test_bundle_delete(cluster):
    bundles = _get_bundle_list(cluster)
    assert bundles, 'no bundles found'
    delete_base_url = '/system/health/v1/report/diagnostics/delete'
    for bundle in bundles:
        cluster.post(os.path.join(delete_base_url, bundle))

    bundles = _get_bundle_list(cluster)
    assert len(bundles) == 0, 'Could not remove bundles {}'.format(bundles)


def test_diagnostics_bundle_status(cluster):
    # validate diagnostics job status response
    diagnostics_bundle_status = cluster.get(path='/system/health/v1/report/diagnostics/status/all').json()
    required_status_fields = ['is_running', 'status', 'errors', 'last_bundle_dir', 'job_started', 'job_ended',
                              'job_duration', 'diagnostics_bundle_dir', 'diagnostics_job_timeout_min',
                              'journald_logs_since_hours', 'diagnostics_job_get_since_url_timeout_min',
                              'command_exec_timeout_sec', 'diagnostics_partition_disk_usage_percent']

    for _, properties in diagnostics_bundle_status.items():
        assert len(properties) == len(required_status_fields), 'response must have the following fields: {}'.format(
            required_status_fields
        )
        for required_status_field in required_status_fields:
            assert required_status_field in properties, 'property {} not found'.format(required_status_field)
