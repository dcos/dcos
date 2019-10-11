import contextlib
import logging
import uuid
from abc import ABC, abstractmethod
from ipaddress import IPv4Address, IPv4Network

import pytest
import test_helpers

from dcos_test_utils import marathon
from test_networking import ensure_routable, MarathonApp, MarathonPod


__maintainer__ = 'mainred'
__contact__ = 'networking-team@mesosphere.io'

log = logging.getLogger(__name__)


class CalicoNetworkTestBase(ABC):
    CALICO_NETWORK_NAME = 'calico'
    NETWORK_TYPE = marathon.Network.USER

    @abstractmethod
    def get_container_type(self):
        return None

    @pytest.fixture(scope="class")
    def slaves(self, dcos_api_session):
        return dcos_api_session.slaves + dcos_api_session.public_slaves

    @pytest.fixture(scope="class")
    def expanded_config(self):
        expanded_config = test_helpers.get_expanded_config()
        return expanded_config

    def get_calico_app(self, host):
        """Returns a calico network application definition with unique id """
        network_name = self.CALICO_NETWORK_NAME
        container_type = self.get_container_type()
        network_type = self.NETWORK_TYPE
        # NOTE: tasks created by marathon in Enterprise DC/OS will be attached
        # with a label DCOS_SPACE: task_id. And calico CNI restricts the length
        # of label value in 63 characters.
        test_uuid = uuid.uuid4().hex[:5]
        app_name_fmt = "/integration-test/calico/app-{}-{}-{}".format(
            str(container_type).lower(), host, test_uuid)
        marathon_app = MarathonApp(
            container=container_type,
            network=network_type,
            host=host,
            network_name=network_name,
            app_name_fmt=app_name_fmt)
        return marathon_app

    @pytest.fixture(scope="class")
    def mesos_calico_apps(self, dcos_api_session, slaves):
        """Returns mesos calico app object in healthy state

        Three applications will be returned if there are more than one slave in
        the cluster, with two on the same slave, and one on another slave.
        In case we have only one slave in the cluster, two applications on the
        same slave will be returned.
        """
        only_one_slave = False
        if len(slaves) == 1:
            log.warn("Only two applications will be returned for only 1 slave"
                     " in the cluster")
            only_one_slave = True
        marathon_apps = []
        app_host0_1 = self.get_calico_app(slaves[0])
        marathon_apps.append(app_host0_1)
        app_host0_2 = self.get_calico_app(slaves[0])
        marathon_apps.append(app_host0_2)
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                dcos_api_session.marathon.deploy_and_cleanup(app_host0_1.app))
            stack.enter_context(
                dcos_api_session.marathon.deploy_and_cleanup(app_host0_2.app))
            if not only_one_slave:
                app_host1 = self.get_calico_app(slaves[1])
                marathon_apps.append(app_host1)
                stack.enter_context(
                    dcos_api_session.marathon.deploy_and_cleanup(
                        app_host1.app))

            yield marathon_apps

    def test_container_in_overlay_network_cidr(
            self, dcos_api_session, mesos_calico_apps, expanded_config):
        network_cidr = expanded_config["calico_network_cidr"]
        for mesos_calico_app in mesos_calico_apps:
            contain_ip_address, _ = mesos_calico_app.hostport(dcos_api_session)
            assert IPv4Address(contain_ip_address) in IPv4Network(network_cidr)

    def test_apps_communication_in_one_node(self, dcos_api_session,
                                            mesos_calico_apps):
        server_app = mesos_calico_apps[0]
        client_app = mesos_calico_apps[1]

        app_host, app_port = server_app.hostport(dcos_api_session)
        cmd = '/opt/mesosphere/bin/curl -s -f -m 5 ' \
              'http://{}:{}/test_uuid'.format(app_host, app_port)
        client_host, client_port = client_app.hostport(dcos_api_session)

        assert ensure_routable(cmd, client_host,
                               client_port)['test_uuid'] == server_app.uuid

    def test_apps_communication_across_nodes(self, dcos_api_session, slaves,
                                             mesos_calico_apps):
        if len(slaves) < 2:
            pytest.skip(
                'Not enough slaves for deploying proxy and origin container'
                ' on different host')
        server_app = mesos_calico_apps[0]
        client_app = mesos_calico_apps[2]

        app_host, app_port = server_app.hostport(dcos_api_session)
        cmd = '/opt/mesosphere/bin/curl -s -f -m 5 ' \
              'http://{}:{}/test_uuid'.format(app_host, app_port)
        client_host, client_port = client_app.hostport(dcos_api_session)
        client_host, client_port = client_app.hostport(dcos_api_session)

        assert ensure_routable(cmd, client_host,
                               client_port)['test_uuid'] == server_app.uuid


class TestCalicoNetworkMesosApp(CalicoNetworkTestBase):
    def get_container_type(self):
        return marathon.Container.MESOS


class TestCalicoNetworkPod(CalicoNetworkTestBase):
    def get_container_type(self):
        return marathon.Container.MESOS

    def get_calico_app(self, host):
        """Returns a calico network pod definition with unique id """
        network_name = self.CALICO_NETWORK_NAME
        container_type = self.get_container_type()
        network_type = self.NETWORK_TYPE
        # NOTE: tasks created by marathon in Enterprise DC/OS will be attached
        # with a label DCOS_SPACE: task_id. And calico CNI restricts the length
        # of label value in 63 characters.
        test_uuid = uuid.uuid4().hex[:5]
        app_name_fmt = "/integration-test/calico/pod-{}-{}-{}".format(
            str(container_type).lower(), host, test_uuid)

        pod = MarathonPod(
            network_type,
            host,
            pod_name_fmt=app_name_fmt,
            network_name=network_name)
        return pod

    @pytest.fixture(scope="class")
    def mesos_calico_apps(self, dcos_api_session, slaves):
        """Returns mesos calico applications in healthy state

        Three applications will be returned if there are more than one slave in
        the cluster, with two on the same slave, and one on another slave.
        In case we have only one slave in the cluster, two applications on the
        same slave will be returned.
        """
        only_one_slave = False
        if len(slaves) == 1:
            log.warn("Only two applications will be returned for only 1 slave"
                     " in the cluster")
            only_one_slave = True
        marathon_pods = []
        app_host0_1 = self.get_calico_app(slaves[0])
        marathon_pods.append(app_host0_1)
        app_host0_2 = self.get_calico_app(slaves[0])
        marathon_pods.append(app_host0_2)
        if not only_one_slave:
            app_host1 = self.get_calico_app(slaves[1])
            marathon_pods.append(app_host1)
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                dcos_api_session.marathon.deploy_pod_and_cleanup(
                    app_host0_1.app))
            stack.enter_context(
                dcos_api_session.marathon.deploy_pod_and_cleanup(
                    app_host0_2.app))
            if not only_one_slave:
                stack.enter_context(
                    dcos_api_session.marathon.deploy_pod_and_cleanup(
                        app_host1.app))

            yield marathon_pods
