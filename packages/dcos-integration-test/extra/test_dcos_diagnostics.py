import datetime
import gzip
import json
import logging
import os
import tempfile
import zipfile

import pytest

import retrying

__maintainer__ = 'mnaboka'
__contact__ = 'dcos-cluster-ops@mesosphere.io'

# Expected latency for all dcos-diagnostics units to refresh after postflight plus
# another minute to allow for check-time to settle. See: DCOS_OSS-988
LATENCY = 120


@pytest.mark.supportedwindows
@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
def test_dcos_diagnostics_health(dcos_api_session):
    """
    test health endpoint /system/health/v1
    """
    required_fields = ['units', 'hostname', 'ip', 'dcos_version', 'node_role', 'mesos_id', 'dcos_diagnostics_version']
    required_fields_unit = ['id', 'health', 'output', 'description', 'help', 'name']

    # Check all masters dcos-diagnostics instances on base port since this is extra-cluster request (outside localhost)
    for host in dcos_api_session.masters:
        response = check_json(dcos_api_session.health.get('/', node=host))
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

    # Check all agents running dcos-diagnostics behind agent-adminrouter on 61001
    for host in dcos_api_session.slaves:
        response = check_json(dcos_api_session.health.get('/', node=host))
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


@pytest.mark.supportedwindows
@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
def test_dcos_diagnostics_nodes(dcos_api_session):
    """
    test a list of nodes with statuses endpoint /system/health/v1/nodes
    """
    for master in dcos_api_session.masters:
        response = check_json(dcos_api_session.health.get('/nodes', node=master))
        assert len(response) == 1, 'nodes response must have only one field: nodes'
        assert 'nodes' in response
        assert isinstance(response['nodes'], list)
        assert len(response['nodes']) == len(dcos_api_session.masters + dcos_api_session.all_slaves), \
            ('a number of nodes in response must be {}'.
             format(len(dcos_api_session.masters + dcos_api_session.all_slaves)))

        # test nodes
        validate_node(response['nodes'])


@pytest.mark.supportedwindows
def test_dcos_diagnostics_nodes_node(dcos_api_session):
    """
    test a specific node enpoint /system/health/v1/nodes/<node>
    """
    for master in dcos_api_session.masters:
        # get a list of nodes
        response = check_json(dcos_api_session.health.get('/nodes', node=master))
        nodes = list(map(lambda node: node['host_ip'], response['nodes']))

        for node in nodes:
            node_response = check_json(dcos_api_session.health.get('/nodes/{}'.format(node), node=master))
            validate_node([node_response])


@pytest.mark.supportedwindows
def test_dcos_diagnostics_nodes_node_units(dcos_api_session):
    """
    test a list of units from a specific node, endpoint /system/health/v1/nodes/<node>/units
    """
    for master in dcos_api_session.masters:
        # get a list of nodes
        response = check_json(dcos_api_session.health.get('/nodes', node=master))
        nodes = list(map(lambda node: node['host_ip'], response['nodes']))

        for node in nodes:
            units_response = check_json(dcos_api_session.health.get('/nodes/{}/units'.format(node), node=master))

            assert len(units_response) == 1, 'unit response should have only 1 field `units`'
            assert 'units' in units_response
            validate_units(units_response['units'])


@pytest.mark.supportedwindows
def test_dcos_diagnostics_nodes_node_units_unit(dcos_api_session):
    """
    test a specific unit for a specific node, endpoint /system/health/v1/nodes/<node>/units/<unit>
    """
    for master in dcos_api_session.masters:
        response = check_json(dcos_api_session.health.get('/nodes', node=master))
        nodes = list(map(lambda node: node['host_ip'], response['nodes']))
        for node in nodes:
            units_response = check_json(dcos_api_session.health.get('/nodes/{}/units'.format(node), node=master))
            unit_ids = list(map(lambda unit: unit['id'], units_response['units']))

            for unit_id in unit_ids:
                validate_unit(
                    check_json(dcos_api_session.health.get('/nodes/{}/units/{}'.format(node, unit_id), node=master)))


@pytest.mark.supportedwindows
@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
def test_dcos_diagnostics_units(dcos_api_session):
    """
    test a list of collected units, endpoint /system/health/v1/units
    """
    # get all unique unit names
    all_units = set()
    for node in dcos_api_session.masters:
        node_response = check_json(dcos_api_session.health.get('/', node=node))
        for unit in node_response['units']:
            all_units.add(unit['id'])

    for node in dcos_api_session.all_slaves:
        node_response = check_json(dcos_api_session.health.get('/', node=node))
        for unit in node_response['units']:
            all_units.add(unit['id'])

    # test against masters
    for master in dcos_api_session.masters:
        units_response = check_json(dcos_api_session.health.get('/units', node=master))
        validate_units(units_response['units'])

        pulled_units = list(map(lambda unit: unit['id'], units_response['units']))
        logging.info('collected units: {}'.format(pulled_units))
        diff = set(pulled_units).symmetric_difference(all_units)
        assert set(pulled_units) == all_units, ('not all units have been collected by dcos-diagnostics '
                                                'puller, missing: {}'.format(diff))


@pytest.mark.supportedwindows
@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
def test_systemd_units_health(dcos_api_session):
    """
    test all units and make sure the units are healthy. This test will fail if any of systemd unit is unhealthy,
    meaning it focuses on making sure the dcos_api_session is healthy, rather then testing dcos-diagnostics itself.
    """
    unhealthy_output = []
    assert dcos_api_session.masters, "Must have at least 1 master node"
    report_response = check_json(dcos_api_session.health.get('/report', node=dcos_api_session.masters[0]))
    assert 'Units' in report_response, "Missing `Units` field in response"
    for unit_name, unit_props in report_response['Units'].items():
        assert 'Health' in unit_props, "Unit {} missing `Health` field".format(unit_name)
        if unit_props['Health'] != 0:
            assert 'Nodes' in unit_props, "Unit {} missing `Nodes` field".format(unit_name)
            assert isinstance(unit_props['Nodes'], list), 'Field `Node` must be a list'
            for node in unit_props['Nodes']:
                assert 'Health' in node, 'Field `Health` is expected to be in nodes properties, got {}'.format(node)
                if node['Health'] != 0:
                    assert 'Output' in node, 'Field `Output` is expected to be in nodes properties, got {}'.format(node)
                    assert isinstance(node['Output'], dict), 'Field `Output` must be a dict'
                    assert unit_name in node['Output'], 'unit {} must be in node Output, got {}'.format(unit_name,
                                                                                                        node['Output'])
                    assert 'IP' in node, 'Field `IP` is expected to be in nodes properties, got {}'.format(node)
                    unhealthy_output.append(
                        'Unhealthy unit {} has been found on node {}, health status {}. journalctl output {}'.format(
                            unit_name, node['IP'], unit_props['Health'], node['Output'][unit_name]))

    if unhealthy_output:
        raise AssertionError('\n'.join(unhealthy_output))


@pytest.mark.supportedwindows
def test_dcos_diagnostics_units_unit(dcos_api_session):
    """
    test a unit response in a right format, endpoint: /system/health/v1/units/<unit>
    """
    for master in dcos_api_session.masters:
        units_response = check_json(dcos_api_session.health.get('/units', node=master))
        pulled_units = list(map(lambda unit: unit['id'], units_response['units']))
        for unit in pulled_units:
            unit_response = check_json(dcos_api_session.health.get('/units/{}'.format(unit), node=master))
            validate_units([unit_response])


@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
def test_dcos_diagnostics_units_unit_nodes(dcos_api_session):
    """
    test a list of nodes for a specific unit, endpoint /system/health/v1/units/<unit>/nodes
    """

    def get_nodes_from_response(response):
        assert 'nodes' in response, 'response must have field `nodes`. Got {}'.format(response)
        nodes_ip_map = make_nodes_ip_map(dcos_api_session)
        nodes = []
        for node in response['nodes']:
            assert 'host_ip' in node, 'node response must have `host_ip` field. Got {}'.format(node)
            assert node['host_ip'] in nodes_ip_map, 'nodes_ip_map must have node {}.Got {}'.format(node['host_ip'],
                                                                                                   nodes_ip_map)
            nodes.append(nodes_ip_map.get(node['host_ip']))
        return nodes

    for master in dcos_api_session.masters:
        units_response = check_json(dcos_api_session.health.get('/units', node=master))
        pulled_units = list(map(lambda unit: unit['id'], units_response['units']))
        for unit in pulled_units:
            nodes_response = check_json(dcos_api_session.health.get('/units/{}/nodes'.format(unit), node=master))
            validate_node(nodes_response['nodes'])

        # make sure dcos-mesos-master.service has master nodes and dcos-mesos-slave.service has agent nodes
        master_nodes_response = check_json(
            dcos_api_session.health.get('/units/dcos-mesos-master.service/nodes', node=master))

        master_nodes = get_nodes_from_response(master_nodes_response)

        assert len(master_nodes) == len(dcos_api_session.masters), \
            '{} != {}'.format(master_nodes, dcos_api_session.masters)
        assert set(master_nodes) == set(dcos_api_session.masters), 'a list of difference: {}'.format(
            set(master_nodes).symmetric_difference(set(dcos_api_session.masters))
        )

        agent_nodes_response = check_json(
            dcos_api_session.health.get('/units/dcos-mesos-slave.service/nodes', node=master))

        agent_nodes = get_nodes_from_response(agent_nodes_response)

        assert len(agent_nodes) == len(dcos_api_session.slaves), '{} != {}'.format(agent_nodes, dcos_api_session.slaves)


@pytest.mark.supportedwindows
def test_dcos_diagnostics_units_unit_nodes_node(dcos_api_session):
    """
    test a specific node for a specific unit, endpoint /system/health/v1/units/<unit>/nodes/<node>
    """
    required_node_fields = ['host_ip', 'health', 'role', 'output', 'help']

    for master in dcos_api_session.masters:
        units_response = check_json(dcos_api_session.health.get('/units', node=master))
        pulled_units = list(map(lambda unit: unit['id'], units_response['units']))
        for unit in pulled_units:
            nodes_response = check_json(dcos_api_session.health.get('/units/{}/nodes'.format(unit), node=master))
            pulled_nodes = list(map(lambda node: node['host_ip'], nodes_response['nodes']))
            logging.info('pulled nodes: {}'.format(pulled_nodes))
            for node in pulled_nodes:
                node_response = check_json(
                    dcos_api_session.health.get('/units/{}/nodes/{}'.format(unit, node), node=master))
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


@pytest.mark.supportedwindows
def test_dcos_diagnostics_selftest(dcos_api_session):
    """
    test invokes dcos-diagnostics `self test` functionality
    """
    for node in dcos_api_session.masters:
        response = check_json(dcos_api_session.health.get('/selftest/info', node=node))
        for test_name, attrs in response.items():
            assert 'Success' in attrs, 'Field `Success` does not exist'
            assert 'ErrorMessage' in attrs, 'Field `ErrorMessage` does not exist'
            assert attrs['Success'], '{} failed, error message {}'.format(test_name, attrs['ErrorMessage'])


@pytest.mark.supportedwindows
def test_dcos_diagnostics_report(dcos_api_session):
    """
    test dcos-diagnostics report endpoint /system/health/v1/report
    """
    for master in dcos_api_session.masters:
        report_response = check_json(dcos_api_session.health.get('/report', node=master))
        assert 'Units' in report_response
        assert len(report_response['Units']) > 0

        assert 'Nodes' in report_response
        assert len(report_response['Nodes']) > 0


def test_dcos_diagnostics_bundle_create_download_delete(dcos_api_session):
    """
    test bundle create, read, delete workflow
    """
    bundle = _create_bundle(dcos_api_session)
    _check_diagnostics_bundle_status(dcos_api_session)
    _download_and_extract_bundle(dcos_api_session, bundle)
    _download_and_extract_bundle_from_another_master(dcos_api_session, bundle)
    _delete_bundle(dcos_api_session, bundle)


def _check_diagnostics_bundle_status(dcos_api_session):
    # validate diagnostics job status response
    diagnostics_bundle_status = check_json(dcos_api_session.health.get('/report/diagnostics/status/all'))
    required_status_fields = ['is_running', 'status', 'errors', 'last_bundle_dir', 'job_started', 'job_ended',
                              'job_duration', 'diagnostics_bundle_dir', 'diagnostics_job_timeout_min',
                              'journald_logs_since_hours', 'diagnostics_job_get_since_url_timeout_min',
                              'command_exec_timeout_sec', 'diagnostics_partition_disk_usage_percent',
                              'job_progress_percentage']

    for _, properties in diagnostics_bundle_status.items():
        assert len(properties) == len(required_status_fields), 'response must have the following fields: {}'.format(
            required_status_fields
        )
        for required_status_field in required_status_fields:
            assert required_status_field in properties, 'property {} not found'.format(required_status_field)


def _create_bundle(dcos_api_session):
    # start the diagnostics bundle job
    create_response = check_json(dcos_api_session.health.post('/report/diagnostics/create', json={"nodes": ["all"]}))

    # make sure the job is done, timeout is 5 sec, wait between retying is 1 sec

    last_datapoint = {
        'time': None,
        'value': 0
    }

    wait_for_diagnostics_job(dcos_api_session, last_datapoint)
    wait_for_diagnostics_list(dcos_api_session)

    # the job should be complete at this point.
    # check the listing for a zip file
    bundles = _get_bundle_list(dcos_api_session)
    assert len(bundles) == 1, 'bundle file not found'
    assert bundles[0] == create_response['extra']['bundle_name']

    return create_response['extra']['bundle_name']


def _delete_bundle(dcos_api_session, bundle):
    bundles = _get_bundle_list(dcos_api_session)
    assert bundle in bundles, 'not found {} in {}'.format(bundle, bundles)

    dcos_api_session.health.post(os.path.join('/report/diagnostics/delete', bundle))

    bundles = _get_bundle_list(dcos_api_session)
    assert bundle not in bundles, 'found {} in {}'.format(bundle, bundles)


@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
def _download_and_extract_bundle(dcos_api_session, bundle):
    _download_bundle_from_master(dcos_api_session, 0, bundle)


@retrying.retry(wait_fixed=2000, stop_max_delay=LATENCY * 1000)
def _download_and_extract_bundle_from_another_master(dcos_api_session, bundle):
    if len(dcos_api_session.masters) > 1:
        _download_bundle_from_master(dcos_api_session, 1, bundle)


def _download_bundle_from_master(dcos_api_session, master_index, bundle):
    """ Download DC/OS diagnostics bundle from a master

    :param dcos_api_session: dcos_api_session fixture
    :param master_index: master index from dcos_api_session.masters array
    :param bundle: bundle name to download from master
    """
    assert len(dcos_api_session.masters) >= master_index + 1, '{} masters required. Got {}'.format(
        master_index + 1, len(dcos_api_session.masters))

    bundles = _get_bundle_list(dcos_api_session)
    assert bundle in bundles, 'not found {} in {}'.format(bundle, bundles)

    expected_common_files = ['dmesg_-T-0.output.gz', 'opt/mesosphere/active.buildinfo.full.json.gz',
                             'opt/mesosphere/etc/dcos-version.json.gz', 'opt/mesosphere/etc/expanded.config.json.gz',
                             'opt/mesosphere/etc/user.config.yaml.gz', 'dcos-diagnostics-health.json',
                             'var/lib/dcos/cluster-id.gz', 'ps_aux_ww-4.output.gz',
                             'proc/cmdline.gz', 'proc/cpuinfo.gz', 'proc/meminfo.gz', 'proc/self/mountinfo.gz',
                             'optmesospherebincurl_-s_-S_http:localhost:62080v1vips-5.output.gz',
                             'timedatectl-6.output.gz', 'binsh_-c_cat etc*-release-7.output.gz',
                             'systemctl_list-units_dcos*-8.output.gz', "iptables-save-9.output.gz"]

    # these files are expected to be in archive for a master host
    expected_master_files = ['dcos-mesos-master.service.gz', 'var/lib/dcos/exhibitor/zookeeper/snapshot/myid.gz',
                             'var/lib/dcos/exhibitor/conf/zoo.cfg.gz', '5050-quota.json',
                             'binsh_-c_cat proc`systemctl show dcos-mesos-master.service -p MainPID'
                             '| cut -d\'=\' -f2`environ-10.output.gz', '5050-overlay-master_state.json.gz'
                             ] + expected_common_files

    expected_agent_common_files = ['5051-containers.json', '5051-overlay-agent_overlay.json',
                                   'binsh_-c_cat proc`systemctl show dcos-mesos-master.service -p MainPID'
                                   '| cut -d\'=\' -f2`environ-11.output.gz']

    # for agent host
    expected_agent_files = ['dcos-mesos-slave.service.gz'
                            ] + expected_agent_common_files + expected_common_files

    # for public agent host
    expected_public_agent_files = ['dcos-mesos-slave-public.service.gz'
                                   ] + expected_agent_common_files + expected_common_files

    def _read_from_zip(z: zipfile.ZipFile, item: str, to_json=True):
        # raises KeyError if item is not in zipfile.
        item_content = z.read(item).decode()

        if to_json:
            # raises ValueError if cannot deserialize item_content.
            return json.loads(item_content)

        return item_content

    def _get_dcos_diagnostics_health(z: zipfile.ZipFile, item: str):
        # try to load dcos-diagnostics health report and validate the report is for this host
        try:
            _health_report = _read_from_zip(z, item)
        except KeyError:
            # we did not find a key in archive, let's take a look at items in archive and try to read
            # diagnostics logs.

            # namelist() gets a list of all items in a zip archive.
            logging.info(z.namelist())

            # summaryErrorsReport.txt and summaryReport.txt are diagnostic job log files.
            for log in ('summaryErrorsReport.txt', 'summaryReport.txt'):
                try:
                    log_data = _read_from_zip(z, log, to_json=False)
                    logging.info("{}:\n{}".format(log, log_data))
                except KeyError:
                    logging.info("Could not read {}".format(log))
            raise

        except ValueError:
            logging.info("Could not deserialize dcos-diagnostics-health")
            raise

        return _health_report

    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_full_location = os.path.join(tmp_dir, bundle)
        with open(bundle_full_location, 'wb') as f:
            r = dcos_api_session.health.get(os.path.join('/report/diagnostics/serve', bundle), stream=True,
                                            node=dcos_api_session.masters[master_index])

            for chunk in r.iter_content(1024):
                f.write(chunk)

        # validate bundle zip file.
        assert zipfile.is_zipfile(bundle_full_location)
        z = zipfile.ZipFile(bundle_full_location)

        # get a list of all files in a zip archive.
        archived_items = z.namelist()

        # validate error log is empty
        if 'summaryErrorsReport.txt' in archived_items:
            log_data = _read_from_zip(z, 'summaryErrorsReport.txt', to_json=False)
            raise AssertionError('summaryErrorsReport.txt must be empty. Got {}'.format(log_data))

        # validate all files in zip archive are not empty
        for item in archived_items:
            assert z.getinfo(item).file_size, 'item {} is empty'.format(item)

        # make sure all required log files for master node are in place.
        for master_ip in dcos_api_session.masters:
            master_folder = master_ip + '_master/'

            # try to load dcos-diagnostics health report and validate the report is for this host
            health_report = _get_dcos_diagnostics_health(z, master_folder + 'dcos-diagnostics-health.json')
            assert 'ip' in health_report
            assert health_report['ip'] == master_ip

            # make sure systemd unit output is correct and does not contain error message
            gzipped_unit_output = z.open(master_folder + 'dcos-mesos-master.service.gz')
            verify_unit_response(gzipped_unit_output, 100)

            verify_archived_items(master_folder, archived_items, expected_master_files)

        # make sure all required log files for agent node are in place.
        for slave_ip in dcos_api_session.slaves:
            agent_folder = slave_ip + '_agent/'

            # try to load dcos-diagnostics health report and validate the report is for this host
            health_report = _get_dcos_diagnostics_health(z, agent_folder + 'dcos-diagnostics-health.json')
            assert 'ip' in health_report
            assert health_report['ip'] == slave_ip

            # make sure systemd unit output is correct and does not contain error message
            gzipped_unit_output = z.open(agent_folder + 'dcos-mesos-slave.service.gz')
            verify_unit_response(gzipped_unit_output, 100)

            verify_archived_items(agent_folder, archived_items, expected_agent_files)

        # make sure all required log files for public agent node are in place.
        for public_slave_ip in dcos_api_session.public_slaves:
            agent_public_folder = public_slave_ip + '_agent_public/'

            # try to load dcos-diagnostics health report and validate the report is for this host
            health_report = _get_dcos_diagnostics_health(z, agent_public_folder + 'dcos-diagnostics-health.json')
            assert 'ip' in health_report
            assert health_report['ip'] == public_slave_ip

            # make sure systemd unit output is correct and does not contain error message
            gzipped_unit_output = z.open(agent_public_folder + 'dcos-mesos-slave-public.service.gz')
            verify_unit_response(gzipped_unit_output, 100)

            verify_archived_items(agent_public_folder, archived_items, expected_public_agent_files)


def _get_bundle_list(dcos_api_session):
    response = check_json(dcos_api_session.health.get('/report/diagnostics/list/all'))
    bundles = []
    for _, bundle_list in response.items():
        if bundle_list is not None and isinstance(bundle_list, list) and len(bundle_list) > 0:
            # append bundles and get just the filename.
            bundles += map(lambda s: os.path.basename(s['file_name']), bundle_list)
    return bundles


def check_json(response):
    response.raise_for_status()
    try:
        json_response = response.json()
        logging.debug('Response: {}'.format(json_response))
    except ValueError:
        logging.exception('Could not deserialize response contents:{}'.format(response.content.decode()))
        raise
    assert len(json_response) > 0, 'Empty JSON returned from dcos-diagnostics request'
    return json_response


def make_nodes_ip_map(dcos_api_session):
    """
    a helper function to make a map detected_ip -> external_ip
    """
    node_private_public_ip_map = {}
    for node in dcos_api_session.masters:
        detected_ip = check_json(dcos_api_session.health.get('/', node=node))['ip']
        node_private_public_ip_map[detected_ip] = node

    for node in dcos_api_session.all_slaves:
        detected_ip = check_json(dcos_api_session.health.get('/', node=node))['ip']
        node_private_public_ip_map[detected_ip] = node

    return node_private_public_ip_map


@retrying.retry(wait_fixed=2000, stop_max_delay=120000,
                retry_on_result=lambda x: x is False)
def wait_for_diagnostics_job(dcos_api_session, last_datapoint):
    response = check_json(dcos_api_session.health.get('/report/diagnostics/status/all'))
    # find if the job is still running
    job_running = False
    percent_done = 0
    for _, attributes in response.items():
        assert 'is_running' in attributes, '`is_running` field is missing in response'
        assert 'job_progress_percentage' in attributes, '`job_progress_percentage` field is missing in response'

        if attributes['is_running']:
            percent_done = attributes['job_progress_percentage']
            logging.info("Job is running. Progress: {}".format(percent_done))
            job_running = True
            break

    # if we ran this bit previously compare the current datapoint with the one we saved
    if last_datapoint['time'] and last_datapoint['value']:
        if percent_done <= last_datapoint['value']:
            assert (datetime.datetime.now() - last_datapoint['time']) < datetime.timedelta(seconds=15), (
                "Job is not progressing"
            )
    last_datapoint['value'] = percent_done
    last_datapoint['time'] = datetime.datetime.now()

    return not job_running


# sometimes it may take extra few seconds to list bundles after the job is finished.
@retrying.retry(stop_max_delay=5000)
def wait_for_diagnostics_list(dcos_api_session):
    assert _get_bundle_list(dcos_api_session), 'get a list of bundles timeout'


def validate_node(nodes):
    assert isinstance(nodes, list), 'input argument must be a list'
    assert len(nodes) > 0, 'input argument cannot be empty'
    required_fields = ['host_ip', 'health', 'role']

    for node in nodes:
        assert len(node) == len(required_fields), 'node should have the following fields: {}. Actual: {}'.format(
            ', '.join(required_fields), node)
        for required_field in required_fields:
            assert required_field in node, '{} must be in node. Actual: {}'.format(required_field, node)

        # host_ip, health, role fields cannot be empty
        assert node['health'] in [0, 1], 'health must be 0 or 1'
        assert node['host_ip'], 'host_ip cannot be empty'
        assert node['role'], 'role cannot be empty'


def validate_units(units):
    assert isinstance(units, list), 'input argument must be list'
    assert len(units) > 0, 'input argument cannot be empty'
    required_fields = ['id', 'name', 'health', 'description']

    for unit in units:
        assert len(unit) == len(required_fields), 'a unit must have the following fields: {}. Actual: {}'.format(
            ', '.join(required_fields), unit)
        for required_field in required_fields:
            assert required_field in unit, 'unit response must have field: {}. Actual: {}'.format(required_field, unit)

        # a unit must have all 3 fields not empty
        assert unit['id'], 'id field cannot be empty'
        assert unit['name'], 'name field cannot be empty'
        assert unit['health'] in [0, 1], 'health must be 0 or 1'
        assert unit['description'], 'description field cannot be empty'


def validate_unit(unit):
    assert isinstance(unit, dict), 'input argument must be a dict'

    required_fields = ['id', 'health', 'output', 'description', 'help', 'name']
    assert len(unit) == len(required_fields), 'unit must have the following fields: {}. Actual: {}'.format(
        ', '.join(required_fields), unit)
    for required_field in required_fields:
        assert required_field in unit, '{} must be in a unit. Actual: {}'.format(required_field, unit)

    # id, name, health, description, help should not be empty
    assert unit['id'], 'id field cannot be empty'
    assert unit['name'], 'name field cannot be empty'
    assert unit['health'] in [0, 1], 'health must be 0 or 1'
    assert unit['description'], 'description field cannot be empty'
    assert unit['help'], 'help field cannot be empty'


def verify_archived_items(folder, archived_items, expected_files):
    for expected_file in expected_files:
        expected_file = folder + expected_file
        assert expected_file in archived_items, ('expecting {} in {}'.format(expected_file, archived_items))


def verify_unit_response(zip_ext_file, min_lines):
    assert isinstance(zip_ext_file, zipfile.ZipExtFile)
    unit_output = gzip.decompress(zip_ext_file.read())
    assert len(unit_output.decode().split('\n')) >= min_lines, 'Expect at least {} lines. Full unit output {}'.format(
        min_lines, unit_output)
