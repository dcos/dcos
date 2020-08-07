"""
Tests for calico network containers Different from tests under
packages/dcos-integration-test/test_calico_networking.py which tests only with
default parameters, current tests also take into consideration scenerios when
different configurations exposed to the operators are enabled.
"""
import uuid
from pathlib import Path
from typing import Iterator

import pytest

from _pytest.fixtures import SubRequest
from cluster_helpers import artifact_dir_format, dump_cluster_journals, wait_for_dcos_oss
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Node, Output
from passlib.hash import sha512_crypt


superuser_username = str(uuid.uuid4())
superuser_password = str(uuid.uuid4())


def assert_system_unit_state(node: Node, unit_name: str, active: bool = True) -> None:
    result = node.run(
        args=["systemctl show {}".format(unit_name)],
        output=Output.LOG_AND_CAPTURE,
        shell=True,
    )
    unit_properties = result.stdout.strip().decode()
    if active:
        assert "ActiveState=active" in unit_properties
    else:
        assert "ActiveState=inactive" in unit_properties
        assert "ConditionResult=no" in unit_properties


@pytest.fixture(scope="module")
def calico_ipip_cluster(docker_backend: Docker, artifact_path: Path,
                        request: SubRequest, log_dir: Path) -> Iterator[Cluster]:
    # Create a relatively large test cluster, since we've seen problems
    # when many agents attempt to create the Docker network. See
    # https://jira.d2iq.com/browse/D2IQ-70674
    with Cluster(
            cluster_backend=docker_backend,
            masters=3,
            agents=8,
            public_agents=8,
    ) as cluster:

        config = {
            "superuser_username": superuser_username,
            # We can hash the password with any `passlib`-based method here.
            # We choose `sha512_crypt` arbitrarily.
            "superuser_password_hash": sha512_crypt.hash(superuser_password),
            "calico_vxlan_enabled": "false",
            "calico_network_cidr": "192.168.128.0/17",
        }
        cluster.install_dcos_from_path(
            dcos_installer=artifact_path,
            dcos_config={
                **cluster.base_config,
                **config,
            },
            output=Output.LOG_AND_CAPTURE,
            ip_detect_path=docker_backend.ip_detect_path,
        )
        wait_for_dcos_oss(
            cluster=cluster,
            request=request,
            log_dir=log_dir,
        )
        yield cluster

        dump_cluster_journals(
            cluster=cluster,
            target_dir=log_dir / artifact_dir_format(request.node.name),
        )


def test_calico_ipip_container_connectivity(calico_ipip_cluster: Cluster) -> None:

    environment_variables = {
        "DCOS_LOGIN_UNAME":
        superuser_username,
        "DCOS_LOGIN_PW":
        superuser_password,
        "MASTER_PUBLIC_IP":
        list(calico_ipip_cluster.masters)[0].public_ip_address,
        "MASTERS_PRIVATE_IPS":
        [node.private_ip_address for node in calico_ipip_cluster.masters],
        "PUBLIC_AGENTS_PRIVATE_IPS":
        [node.public_ip_address for node in calico_ipip_cluster.public_agents],
        "PRIVATE_AGENTS_PRIVATE_IPS":
        [node.private_ip_address for node in calico_ipip_cluster.agents],
    }

    pytest_command = [
        "pytest",
        "-vvv",
        "-s",
        "-x",
        "test_networking.py",
        "-k",
        "test_calico",
    ]
    calico_ipip_cluster.run_with_test_environment(
        args=pytest_command,
        env=environment_variables,
        output=Output.LOG_AND_CAPTURE,
    )


def test_calico_ipip_unit_active(calico_ipip_cluster: Cluster) -> None:
    calico_units = ["dcos-calico-felix", "dcos-calico-bird", "dcos-calico-confd"]
    for node in calico_ipip_cluster.masters | calico_ipip_cluster.agents | calico_ipip_cluster.public_agents:
        for unit_name in calico_units:
            assert_system_unit_state(node, unit_name, active=True)
