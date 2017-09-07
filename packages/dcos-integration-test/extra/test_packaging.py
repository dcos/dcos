import logging

import pytest

log = logging.getLogger(__name__)


def test_pkgpanda_api(dcos_api_session):

    def get_and_validate_package_ids(path, node):
        r = dcos_api_session.get(path, node=node)
        assert r.status_code == 200
        package_ids = r.json()
        assert isinstance(package_ids, list)
        for package_id in package_ids:
            r = dcos_api_session.get(path + package_id, node=node)
            assert r.status_code == 200
            name, version = package_id.split('--')
            assert r.json() == {'id': package_id, 'name': name, 'version': version}
        return package_ids

    active_buildinfo = dcos_api_session.get('/pkgpanda/active.buildinfo.full.json').json()
    active_buildinfo_packages = sorted(
        # Setup packages don't have a buildinfo.
        (package_name, info['package_version'] if info else None)
        for package_name, info in active_buildinfo.items()
    )

    def assert_packages_match_active_buildinfo(package_ids):
        packages = sorted(map(lambda id_: tuple(id_.split('--')), package_ids))
        assert len(packages) == len(active_buildinfo_packages)
        for package, buildinfo_package in zip(packages, active_buildinfo_packages):
            if buildinfo_package[1] is None:
                # No buildinfo for this package, so we can only compare names.
                assert package[0] == buildinfo_package[0]
            else:
                assert package == buildinfo_package

    for node in dcos_api_session.masters + dcos_api_session.all_slaves:
        package_ids = get_and_validate_package_ids('pkgpanda/repository/', node)
        active_package_ids = get_and_validate_package_ids('pkgpanda/active/', node)

        assert set(active_package_ids) <= set(package_ids)
        assert_packages_match_active_buildinfo(active_package_ids)


# There is no standardized way of getting package requirements from the package description json,
# e.g. nodes could be called 'brokers' or 'nodes' or something else. This was created by looking at
# https://github.com/mesosphere/universe/blob/version-3.x/repo/packages/K/kafka/39/config.json
# 1.1.9-0.10.0.0
KAFKA_PACKAGE_REQUIREMENTS = {
    'number_of_nodes': 3,
    'node': {
        'disk': 5000,
        'mem': 2304,
        'cpus': 1
    },
    'executor': {
        'disk': 0,
        'mem': 256,
        'cpus': 0.5
    }
}


def _get_cluster_resources(dcos_api_session):
    """Return the mesos state summary
    """
    r = dcos_api_session.get('mesos/state-summary')
    return r.json()


def _agent_has_resources(agent, node_requirements):
    """Check that an agent has at least as much resources as requried for one node

    Args:
        agent: dict Info for one 'slave' from the mesos state summary
        node_requirements: dict Resource requirements per agent
    """
    unreserved = agent['unreserved_resources']
    resources = ['mem', 'disk', 'cpus']
    for resource in resources:
        log.debug('{resource}: unreserved {unreserved}, required {required}'.format(
            resource=resource,
            unreserved=unreserved[resource],
            required=node_requirements[resource]))
        if unreserved[resource] < node_requirements[resource]:
            log.debug('Agent does not have has enough {}'.format(resource))
            return False
    return True


def _enough_resources_for_package(state_summary, package_requirements):
    """Sanity check that there are enough unreserved_resources in a state to run a package.

    Args:
        state_summary: dict
        package_requirements: dict

    Returns:
        bool

    Notes:
        This is a sanity check meant for use with pytest.mark.skipif
        This only verifies that there were enough resources at the time state_summary was queried
    """
    agents = state_summary['slaves']
    if len(agents) < package_requirements['number_of_nodes']:
        log.debug('Not enough agents for this package. Need {required}, have {available}'.format(
            required=package_requirements['number_of_nodes'],
            available=len(agents)))
        return False
    usable_nodes = 0
    for agent in agents:
        if _agent_has_resources(agent, package_requirements['node']):
            usable_nodes += 1
        if usable_nodes == package_requirements['number_of_nodes']:
            return True
    log.info('Only {available} usable agents. This package needs {required} with these resources {resources}.'.format(
        available=usable_nodes,
        required=package_requirements['number_of_nodes'],
        resources=package_requirements['node']))
    return False


def _skipif_insufficient_resources(dcos_api_session, requirements):
    """Can't access dcos_api_session from through the pytest.mark.skipif decorator, so call this in each test instead
    """
    if not _enough_resources_for_package(_get_cluster_resources(dcos_api_session), requirements):
        return pytest.skip(msg='Package installation would fail on this cluster due to insufficient resources')


def test_packaging_api(dcos_api_session):
    """Test the Cosmos API (/package) wrapper
    """
    _skipif_insufficient_resources(dcos_api_session, KAFKA_PACKAGE_REQUIREMENTS)
    install_response = dcos_api_session.cosmos.install_package('kafka', package_version='1.1.9-0.10.0.0')
    data = install_response.json()

    dcos_api_session.marathon.poll_marathon_for_app_deployment(data['appId'], 1,
                                                               True, False)

    list_response = dcos_api_session.cosmos.list_packages()
    packages = list_response.json()['packages']
    assert len(packages) == 1 and packages[0]['appId'] == data['appId']

    dcos_api_session.cosmos.uninstall_package('kafka', app_id=data['appId'])

    list_response = dcos_api_session.cosmos.list_packages()
    packages = list_response.json()['packages']
    assert len(packages) == 0
